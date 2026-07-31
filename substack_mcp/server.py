#!/usr/bin/env python3
"""
Substack MCP Server using official MCP SDK

Model Context Protocol server for Substack integration.
Provides tools for creating, editing, and publishing Substack posts.
"""

import json
import os
import sys
from datetime import datetime
from typing import Any, Optional
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from substack_client import SubstackClient, SubstackDocument, MarkdownToSubstack

import mcp.types as types
from mcp.server import Server
from mcp.server.stdio import stdio_server

# Create server instance
server = Server("substack")

# Global state
client: Optional[SubstackClient] = None
live_session: Optional[dict] = None


def init_client():
    """Initialize Substack client from environment"""
    global client
    token = os.getenv("SUBSTACK_SID", "")
    publication = os.getenv("SUBSTACK_PUBLICATION", "")

    if token and publication:
        try:
            client = SubstackClient(token, publication)
            if client.test_connection():
                print(f"Connected to Substack: {publication}", file=sys.stderr)
            else:
                print("Substack connection test failed", file=sys.stderr)
                client = None
        except Exception as e:
            print(f"Failed to initialize Substack client: {e}", file=sys.stderr)
            client = None


def _parse_draft_body(draft_data: dict) -> tuple[Optional[dict], Optional[str]]:
    # Substack returns current content in "body_json" (parsed) and may also
    # keep the raw submission in "draft_body".  Prefer body_json because the
    # API clears / stops updating draft_body after it processes the content.
    raw_body = draft_data.get("body_json") or draft_data.get("draft_body")
    if raw_body is None or raw_body == "":
        return {"type": "doc", "content": []}, None
    if isinstance(raw_body, dict):
        body_json = raw_body
    elif isinstance(raw_body, str):
        try:
            body_json = json.loads(raw_body)
        except Exception as exc:
            return None, f"Could not parse draft body JSON: {exc}"
    else:
        return None, f"Unsupported draft_body type: {type(raw_body).__name__}"

    if not isinstance(body_json, dict):
        return None, "Draft body JSON is not an object"
    if body_json.get("type") != "doc":
        body_json["type"] = "doc"
    if not isinstance(body_json.get("content"), list):
        body_json["content"] = []
    return body_json, None


# --- CHA-295 duplicate-reply guard ---------------------------------------------
# Substack nests replies under "children". The all-comments sweep threw that tree
# away, so an amnesiac run could not see its own past replies and answered the
# same reader repeatedly -- four times, in the worst observed case, and a reader
# asked publicly why. These helpers exist so the answer state is a computed fact
# rather than something the caller is trusted to have remembered.

def _kids(cm: dict) -> list:
    """Substack has used both keys depending on endpoint. Accept either."""
    return (cm.get("children") or cm.get("replies") or []) if isinstance(cm, dict) else []


def _my_replies_under(cm: dict, me: int) -> list:
    """IDs of my replies anywhere in the subtree BELOW cm (not cm itself).

    Deliberately searches the whole subtree, not just direct children: a reply of
    mine nested three deep still means this reader has heard from me.
    """
    found = []

    def walk(node):
        for child in _kids(node):
            if not isinstance(child, dict):
                continue
            if child.get("user_id") == me:
                found.append(child.get("id"))
            walk(child)

    walk(cm)
    return found


def _find_comment(comments: list, cid: int):
    """Locate a comment by id anywhere in a thread tree. None if absent."""
    for c in comments or []:
        if not isinstance(c, dict):
            continue
        if c.get("id") == cid:
            return c
        hit = _find_comment(_kids(c), cid)
        if hit is not None:
            return hit
    return None


def _err(msg: str):
    return [types.TextContent(type="text", text=json.dumps({"error": msg}, indent=2))]
# -------------------------------------------------------------------------------


@server.list_tools()
async def list_tools() -> list[types.Tool]:
    """List available tools"""
    return [
        types.Tool(
            name="substack_create_draft",
            description="Create a new Substack draft post",
            inputSchema={
                "type": "object",
                "properties": {
                    "title": {"type": "string", "description": "Post title"},
                    "subtitle": {"type": "string", "description": "Post subtitle (optional)"},
                    "body": {"type": "string", "description": "Markdown content for the post body"},
                    "audience": {
                        "type": "string",
                        "enum": ["everyone", "only_paid", "founding"],
                        "default": "everyone",
                        "description": "Who can read this post"
                    }
                },
                "required": ["title"]
            }
        ),
        types.Tool(
            name="substack_update_draft",
            description="Update an existing draft's content",
            inputSchema={
                "type": "object",
                "properties": {
                    "draft_id": {"type": "integer", "description": "Draft ID to update"},
                    "title": {"type": "string", "description": "New title (optional)"},
                    "subtitle": {"type": "string", "description": "New subtitle (optional)"},
                    "body": {"type": "string", "description": "New markdown content (replaces existing)"}
                },
                "required": ["draft_id"]
            }
        ),
        types.Tool(
            name="substack_append_to_draft",
            description="Append content to an existing draft (for live blogging)",
            inputSchema={
                "type": "object",
                "properties": {
                    "draft_id": {"type": "integer", "description": "Draft ID"},
                    "content": {"type": "string", "description": "Markdown content to append"},
                    "section_title": {"type": "string", "description": "Optional section header"},
                    "add_timestamp": {"type": "boolean", "default": True, "description": "Add timestamp"}
                },
                "required": ["draft_id", "content"]
            }
        ),
        types.Tool(
            name="substack_add_code_block",
            description="Add a code block to a draft",
            inputSchema={
                "type": "object",
                "properties": {
                    "draft_id": {"type": "integer"},
                    "code": {"type": "string", "description": "Code content"},
                    "language": {"type": "string", "description": "Programming language"},
                    "filename": {"type": "string", "description": "Optional filename"},
                    "caption": {"type": "string", "description": "Optional caption/explanation"}
                },
                "required": ["draft_id", "code"]
            }
        ),
        types.Tool(
            name="substack_add_image",
            description="Add an image to a draft",
            inputSchema={
                "type": "object",
                "properties": {
                    "draft_id": {"type": "integer"},
                    "url": {"type": "string", "description": "Image URL"},
                    "caption": {"type": "string", "description": "Image caption"},
                    "alt": {"type": "string", "description": "Alt text"}
                },
                "required": ["draft_id", "url"]
            }
        ),
        types.Tool(
            name="substack_publish",
            description="Publish a draft to your Substack",
            inputSchema={
                "type": "object",
                "properties": {
                    "draft_id": {"type": "integer", "description": "Draft ID to publish"},
                    "send_email": {"type": "boolean", "default": False, "description": "Email to subscribers"}
                },
                "required": ["draft_id"]
            }
        ),
        types.Tool(
            name="substack_post_note",
            description="Post a short note (like a tweet)",
            inputSchema={
                "type": "object",
                "properties": {
                    "text": {"type": "string", "description": "Note content"},
                    "link_url": {"type": "string", "description": "Optional link to attach"}
                },
                "required": ["text"]
            }
        ),
        types.Tool(
            name="substack_get_drafts",
            description="List all drafts",
            inputSchema={"type": "object", "properties": {}}
        ),
        types.Tool(
            name="substack_get_posts",
            description="List published posts",
            inputSchema={
                "type": "object",
                "properties": {
                    "limit": {"type": "integer", "default": 10, "description": "Max posts to return"}
                }
            }
        ),
        types.Tool(
            name="substack_get_comments",
            description="Get the comment thread for a post (by post_id).",
            inputSchema={
                "type": "object",
                "properties": {
                    "post_id": {"type": "integer", "description": "The post id to read comments from"}
                },
                "required": ["post_id"]
            }
        ),
        types.Tool(
            name="substack_get_all_comments",
            description="Sweep comments across ALL published posts, tagged with post title/id. Use to find fan comments needing a reply.",
            inputSchema={"type": "object", "properties": {}}
        ),
        types.Tool(
            name="substack_reply_to_comment",
            description=(
                "Reply to a comment (or post a top-level comment). OUTWARD-FACING: posts publicly as you. "
                "Omit parent_id for a top-level comment; set it to reply to a specific comment. "
                "GUARDED: if parent_id already has a reply from you anywhere beneath it, this REFUSES "
                "and tells you which replies exist (CHA-295). One reply per comment is the ceiling."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "post_id": {"type": "integer", "description": "The post id the comment lives on"},
                    "body": {"type": "string", "description": "Your reply text"},
                    "parent_id": {"type": "integer", "description": "Comment id to reply to (omit for top-level)"},
                    "force": {
                        "type": "boolean",
                        "description": (
                            "Override the already-answered block. Only set this after reading the "
                            "thread and being certain a second reply is warranted -- e.g. never, in "
                            "practice. Under-replying is harmless; over-replying is public and permanent."
                        ),
                    },
                },
                "required": ["post_id", "body"]
            }
        ),
        types.Tool(
            name="substack_live_blog_start",
            description="Start a live blogging session",
            inputSchema={
                "type": "object",
                "properties": {
                    "title": {"type": "string", "description": "Live blog title"},
                    "subtitle": {"type": "string", "description": "Subtitle"}
                },
                "required": ["title"]
            }
        ),
        types.Tool(
            name="substack_live_blog_end",
            description="End the current live blogging session",
            inputSchema={
                "type": "object",
                "properties": {
                    "publish": {"type": "boolean", "default": False, "description": "Publish on end"}
                }
            }
        )
    ]


@server.call_tool()
async def call_tool(name: str, arguments: dict) -> list[types.TextContent]:
    """Execute a tool call"""
    global client, live_session

    if not client:
        return [types.TextContent(type="text", text=json.dumps({"error": "Substack client not initialized. Set SUBSTACK_SID and SUBSTACK_PUBLICATION."}))]

    try:
        result = {}

        if name == "substack_create_draft":
            title = arguments.get("title", "Untitled")
            subtitle = arguments.get("subtitle", "")
            body = arguments.get("body", "")
            audience = arguments.get("audience", "everyone")

            draft = client.create_draft(
                title=title,
                subtitle=subtitle,
                body=body,
                audience=audience
            )

            result = {
                "success": True,
                "draft_id": draft.id,
                "title": draft.title,
                "edit_url": f"https://{client.publication}/publish/post/{draft.id}"
            }

        elif name == "substack_update_draft":
            draft_id = arguments.get("draft_id")
            client.update_draft(
                draft_id=draft_id,
                title=arguments.get("title"),
                subtitle=arguments.get("subtitle"),
                body=arguments.get("body")
            )
            result = {"success": True, "draft_id": draft_id, "message": "Draft updated"}

        elif name == "substack_append_to_draft":
            draft_id = arguments.get("draft_id")
            content = arguments.get("content", "")
            section_title = arguments.get("section_title")
            add_timestamp = arguments.get("add_timestamp", True)

            draft_data = client.get_draft(draft_id)
            body_json, error = _parse_draft_body(draft_data)
            if error:
                return [types.TextContent(type="text", text=json.dumps({"error": error}))]

            new_content = []
            if section_title:
                timestamp = ""
                if add_timestamp:
                    timestamp = f" ({datetime.now().strftime('%I:%M %p')})"
                new_content.append({
                    "type": "heading",
                    "attrs": {"level": 3},
                    "content": [{"type": "text", "text": f"{section_title}{timestamp}"}]
                })

            converted = MarkdownToSubstack.convert(content)
            new_content.extend(converted.get("content", []))
            body_json["content"].extend(new_content)
            client.update_draft(draft_id=draft_id, body=body_json)
            if live_session and live_session.get("draft_id") == draft_id:
                live_session["updates"] = live_session.get("updates", 0) + 1

            result = {
                "success": True,
                "draft_id": draft_id,
                "message": "Content appended",
                "total_sections": len([n for n in body_json["content"] if n.get("type") == "heading"])
            }

        elif name == "substack_add_code_block":
            draft_id = arguments.get("draft_id")
            code = arguments.get("code", "")
            language = arguments.get("language", "")
            filename = arguments.get("filename", "")
            caption = arguments.get("caption", "")

            draft_data = client.get_draft(draft_id)
            body_json, error = _parse_draft_body(draft_data)
            if error:
                return [types.TextContent(type="text", text=json.dumps({"error": error}))]

            if filename:
                body_json["content"].append({
                    "type": "paragraph",
                    "content": [{"type": "text", "text": f"📄 {filename}", "marks": [{"type": "code"}]}]
                })

            body_json["content"].append({
                "type": "codeBlock",
                "attrs": {"language": language},
                "content": [{"type": "text", "text": code}]
            })

            if caption:
                body_json["content"].append({
                    "type": "paragraph",
                    "content": [{"type": "text", "text": caption, "marks": [{"type": "em"}]}]
                })

            client.update_draft(draft_id=draft_id, body=body_json)
            if live_session and live_session.get("draft_id") == draft_id:
                live_session["updates"] = live_session.get("updates", 0) + 1
            result = {"success": True, "message": "Code block added"}

        elif name == "substack_add_image":
            draft_id = arguments.get("draft_id")
            url = arguments.get("url")
            caption = arguments.get("caption", "")
            alt = arguments.get("alt", "")

            draft_data = client.get_draft(draft_id)
            body_json, error = _parse_draft_body(draft_data)
            if error:
                return [types.TextContent(type="text", text=json.dumps({"error": error}))]

            image_doc = SubstackDocument()
            image_doc.image(url, alt=alt, caption=caption)
            body_json["content"].extend(image_doc.build()["content"])

            client.update_draft(draft_id=draft_id, body=body_json)
            if live_session and live_session.get("draft_id") == draft_id:
                live_session["updates"] = live_session.get("updates", 0) + 1
            result = {"success": True, "message": "Image added"}

        elif name == "substack_publish":
            draft_id = arguments.get("draft_id")
            send_email = arguments.get("send_email", False)
            pub_result = client.publish_draft(draft_id, send_email=send_email)
            result = {"success": True, "url": pub_result.get("canonical_url", ""), "email_sent": send_email}

        elif name == "substack_post_note":
            text = arguments.get("text", "")
            link_url = arguments.get("link_url")
            if link_url:
                note_result = client.post_note_with_link(text, link_url)
            else:
                note_result = client.post_note(text)
            result = {"success": True, "note_id": note_result.get("id"), "message": "Note posted"}

        elif name == "substack_get_drafts":
            drafts = client.get_drafts()
            result = {"drafts": [{"id": d.id, "title": d.title or "(Untitled)", "subtitle": d.subtitle} for d in drafts]}

        elif name == "substack_get_posts":
            limit = arguments.get("limit", 10)
            posts = client.get_archive(limit=limit)
            result = {"posts": [{"id": p.id, "title": p.title, "url": p.canonical_url, "date": p.post_date} for p in posts]}

        elif name == "substack_get_comments":
            post_id = arguments["post_id"]
            comments = client.get_comments(post_id)
            def _fmt(cm):
                return {
                    "id": cm.get("id"),
                    "name": cm.get("name"),
                    "handle": cm.get("handle"),
                    "user_id": cm.get("user_id"),
                    "date": cm.get("date"),
                    "body": cm.get("body"),
                    "replies": [_fmt(ch) for ch in (cm.get("children") or [])],
                }
            result = {"post_id": post_id, "comments": [_fmt(c) for c in comments]}

        elif name == "substack_get_all_comments":
            rows = client.get_all_comments()
            me = client.get_user_id()
            items = []
            for r in rows:
                cm = r["comment"]
                mine = _my_replies_under(cm, me)
                items.append({
                    "post_id": r["post_id"],
                    "post_title": r["post_title"],
                    "comment_id": cm.get("id"),
                    "name": cm.get("name"),
                    "handle": cm.get("handle"),
                    "user_id": cm.get("user_id"),
                    "date": cm.get("date"),
                    "body": cm.get("body"),
                    # CHA-295: this sweep used to drop children entirely, so a fresh
                    # amnesiac run could not distinguish an answered comment from an
                    # unanswered one, and cheerfully answered it again. Readers
                    # noticed before I did. These two fields are the read-layer fix.
                    "answered_by_me": bool(mine),
                    "my_reply_ids": mine,
                })
            unanswered = sum(1 for i in items if not i["answered_by_me"])
            result = {
                "total": len(items),
                "unanswered": unanswered,
                "note": "answered_by_me=true means SKIP IT (CHA-295).",
                "items": items,
            }

        elif name == "substack_reply_to_comment":
            post_id = arguments["post_id"]
            body = arguments["body"]
            parent_id = arguments.get("parent_id")

            # ---- CHA-295 HARD GATE -------------------------------------------
            # The rule "check the thread before replying" lived in a prompt for
            # seven weeks and was skimmed anyway -- I double-replied to a reader
            # on 2026-07-28 with the rule sitting right there in my instructions.
            # A guard that can be skimmed is not a guard. So it moved into the
            # action: this call now REFUSES rather than trusting the caller to
            # have checked. Over-replying is publicly embarrassing and cannot be
            # undone; under-replying is harmless. Fail closed.
            if parent_id is not None and not arguments.get("force"):
                try:
                    me = client.get_user_id()
                    parent = _find_comment(client.get_comments(post_id), parent_id)
                except Exception as e:
                    return _err(f"Refusing to reply: could not verify whether comment "
                                f"{parent_id} was already answered ({e}). An unverifiable "
                                f"thread is not an empty one. Pass force=true to override.")
                if parent is None:
                    return _err(f"Refusing to reply: comment {parent_id} was not found in "
                                f"post {post_id}. Not found is not the same as not answered. "
                                f"Pass force=true to override.")
                existing = _my_replies_under(parent, me)
                if existing:
                    return _err(
                        f"BLOCKED (CHA-295): I have already replied to comment {parent_id}. "
                        f"My existing repl{'y' if len(existing)==1 else 'ies'}: {existing}. "
                        f"One reply per comment is the ceiling. If they have since posted a "
                        f"NEW child comment, reply to THAT comment's id instead -- nested, "
                        f"not a fresh re-reply to the parent. Pass force=true only if you "
                        f"have read the thread and are certain."
                    )
            # -------------------------------------------------------------------

            reply = client.reply_to_comment(post_id, body, parent_id)
            result = {"posted": True, "post_id": post_id, "parent_id": parent_id,
                      "comment_id": reply.get("id") if isinstance(reply, dict) else None}

        elif name == "substack_live_blog_start":
            title = arguments.get("title", f"Live Blog - {datetime.now().strftime('%Y-%m-%d')}")
            subtitle = arguments.get("subtitle", "")

            doc = SubstackDocument()
            doc.paragraph("🔴 ", doc.bold("Live Blog Started"), f" - {datetime.now().strftime('%I:%M %p')}")
            doc.horizontal_rule()

            draft = client.create_draft(title=title, subtitle=subtitle, body=doc)

            live_session = {
                "draft_id": draft.id,
                "title": title,
                "started_at": datetime.now().isoformat(),
                "updates": 0,
                "active": True
            }

            result = {
                "success": True,
                "session": live_session,
                "edit_url": f"https://{client.publication}/publish/post/{draft.id}"
            }

        elif name == "substack_live_blog_end":
            if not live_session:
                result = {"error": "No active live blog session"}
            else:
                draft_id = live_session["draft_id"]
                publish = arguments.get("publish", False)

                # Append closing
                draft_data = client.get_draft(draft_id)
                body_json, error = _parse_draft_body(draft_data)
                if error:
                    return [types.TextContent(type="text", text=json.dumps({"error": error}))]

                closing_doc = SubstackDocument()
                closing_doc.paragraph("🔴 ", closing_doc.bold("Live Blog Ended"), f" - {datetime.now().strftime('%I:%M %p')}")
                body_json["content"].extend(closing_doc.build()["content"])
                client.update_draft(draft_id=draft_id, body=body_json)

                result = {"success": True, "session": live_session, "published": False}

                if publish:
                    pub_result = client.publish_draft(draft_id, send_email=False)
                    result["published"] = True
                    result["url"] = pub_result.get("canonical_url")

                live_session = None

        else:
            result = {"error": f"Unknown tool: {name}"}

        return [types.TextContent(type="text", text=json.dumps(result, indent=2))]

    except Exception as e:
        return [types.TextContent(type="text", text=json.dumps({"error": str(e)}))]


@server.list_resources()
async def list_resources() -> list[types.Resource]:
    """List available resources"""
    return [
        types.Resource(uri="substack://drafts", name="Substack Drafts", description="List of all draft posts", mimeType="application/json"),
        types.Resource(uri="substack://posts", name="Substack Posts", description="List of published posts", mimeType="application/json"),
        types.Resource(uri="substack://profile", name="Substack Profile", description="Your Substack profile", mimeType="application/json"),
        types.Resource(uri="substack://live-session", name="Live Blog Session", description="Current live blogging session state", mimeType="application/json")
    ]


@server.read_resource()
async def read_resource(uri: str) -> str:
    """Read a resource"""
    global client, live_session

    if not client:
        return json.dumps({"error": "Client not initialized"})

    if uri == "substack://drafts":
        drafts = client.get_drafts()
        return json.dumps([{"id": d.id, "title": d.title, "subtitle": d.subtitle} for d in drafts], indent=2)

    elif uri == "substack://posts":
        posts = client.get_archive(limit=20)
        return json.dumps([{"id": p.id, "title": p.title, "url": p.canonical_url} for p in posts], indent=2)

    elif uri == "substack://profile":
        profile = client.get_profile()
        return json.dumps({"id": profile.id, "name": profile.name, "handle": profile.handle, "url": profile.url}, indent=2)

    elif uri == "substack://live-session":
        return json.dumps(live_session or {"active": False}, indent=2)

    return json.dumps({"error": f"Unknown resource: {uri}"})


async def _main():
    """Async entry point"""
    init_client()
    async with stdio_server() as (read_stream, write_stream):
        await server.run(read_stream, write_stream, server.create_initialization_options())


def main():
    """Console script entry point"""
    import asyncio
    asyncio.run(_main())


if __name__ == "__main__":
    main()
