#!/usr/bin/env python3
"""
Load all conversations from memory-talk server into mem0.
"""

import json
import sys
from datetime import datetime
from pathlib import Path

import requests
from mem0 import MemoryClient

API_URL = "http://localhost:7788"


def get_all_conversations():
    """Fetch all conversations from the API."""
    response = requests.get(f"{API_URL}/api/conversations", timeout=30)
    response.raise_for_status()
    return response.json()


def get_conversation(platform: str, session_id: str):
    """Fetch a single conversation with messages."""
    response = requests.get(f"{API_URL}/api/conversations/{platform}/{session_id}", timeout=30)
    response.raise_for_status()
    return response.json()


def format_message_for_mem0(msg: dict, metadata: dict) -> str:
    """Format a message for mem0 memory."""
    role = msg.get("role", "unknown")
    content = msg.get("content", "")
    timestamp = msg.get("timestamp", "")

    # Extract project path from metadata
    project_path = metadata.get("metadata", {}).get("project_path", "unknown")

    # Format as a memory with context
    return f"[{role.upper()}] {content}"


MAX_CHARS = 50000  # ~100k tokens limit with safety margin


def chunk_messages(messages: list, max_chars: int = MAX_CHARS) -> list[list]:
    """Split messages into chunks that fit within token limits."""
    chunks = []
    current_chunk = []
    current_chars = 0

    for msg in messages:
        role = msg.get("role", "unknown")
        content = msg.get("content", "")
        # Truncate very long individual messages
        if len(content) > 10000:
            content = content[:10000] + "... [truncated]"

        msg_str = f"{role.upper()}: {content}\n\n"
        msg_len = len(msg_str)

        # If single message exceeds limit, skip it
        if msg_len > max_chars:
            continue

        # Check if adding this message would exceed limit
        if current_chars + msg_len > max_chars and current_chunk:
            chunks.append(current_chunk)
            current_chunk = []
            current_chars = 0

        current_chunk.append(msg)
        current_chars += msg_len

    # Don't forget the last chunk
    if current_chunk:
        chunks.append(current_chunk)

    return chunks


def load_to_mem0(conversations: list, client: MemoryClient, user_id: str = "memory-talk"):
    """Load all conversations to mem0."""
    total_messages = 0
    total_memories = 0

    for conv in conversations:
        platform = conv.get("platform")
        session_id = conv.get("session_id")
        title = conv.get("title", "Untitled")

        print(f"Processing: {title} ({session_id})")

        try:
            # Get full conversation with messages
            conv_data = get_conversation(platform, session_id)
            metadata = conv_data.get("metadata", {})
            messages = conv_data.get("messages", [])

            # Build conversation context
            project_path = metadata.get("project_path", "unknown")

            if not messages:
                continue

            # Chunk messages to avoid token limits
            message_chunks = chunk_messages(messages)
            print(f"  -> Split into {len(message_chunks)} chunks")

            for i, chunk in enumerate(message_chunks):
                # Create memory for this chunk
                conversation_text = f"Conversation: {title}\n"
                conversation_text += f"Project: {project_path}\n"
                conversation_text += f"Platform: {platform}\n"
                conversation_text += f"Date: {metadata.get('created_at', '')}\n"
                conversation_text += f"Chunk: {i+1}/{len(message_chunks)}\n\n"

                for msg in chunk:
                    role = msg.get("role", "unknown")
                    content = msg.get("content", "")
                    conversation_text += f"{role.upper()}: {content}\n\n"
                    total_messages += 1

                # Add to mem0
                if conversation_text.strip():
                    try:
                        client.add(
                            messages=[{"role": "user", "content": conversation_text}],
                            user_id=user_id,
                            metadata={
                                "platform": platform,
                                "session_id": session_id,
                                "title": title,
                                "project_path": project_path,
                                "message_count": len(messages),
                                "chunk": i + 1,
                                "total_chunks": len(message_chunks),
                            }
                        )
                        total_memories += 1
                    except Exception as e:
                        print(f"  -> Error adding chunk {i+1} to mem0: {e}", file=sys.stderr)

            print(f"  -> Added {len(messages)} messages ({len(message_chunks)} chunks) to mem0")

        except Exception as e:
            print(f"  -> Error processing conversation: {e}", file=sys.stderr)
            continue

    return total_messages, total_memories


def main():
    """Main function."""
    import argparse

    parser = argparse.ArgumentParser(description="Load conversations from memory-talk to mem0")
    parser.add_argument(
        "--api-key",
        required=True,
        help="mem0 API key (e.g., m0-...)",
    )
    parser.add_argument(
        "--url",
        default=API_URL,
        help=f"memory-talk API URL (default: {API_URL})",
    )
    parser.add_argument(
        "--user-id",
        default="memory-talk",
        help="User ID for mem0 (default: memory-talk)",
    )
    parser.add_argument(
        "--platform",
        help="Filter by platform (e.g., claude-code)",
    )

    args = parser.parse_args()

    # Check API availability
    try:
        response = requests.get(f"{args.url}/api/status", timeout=5)
        if response.status_code != 200:
            print(f"API error: {response.status_code}")
            sys.exit(1)
        status = response.json()
        print(f"Connected to {args.url}")
        print(f"Total conversations: {status.get('total_conversations', 0)}")
        print(f"Total messages: {status.get('total_messages', 0)}")
    except requests.exceptions.RequestException as e:
        print(f"Cannot connect to API at {args.url}: {e}")
        sys.exit(1)

    # Initialize mem0 client
    try:
        client = MemoryClient(api_key=args.api_key)
        print(f"Connected to mem0")
    except Exception as e:
        print(f"Error initializing mem0 client: {e}")
        sys.exit(1)

    # Get all conversations
    print("\nFetching conversations...")
    all_conversations = get_all_conversations()

    # Filter by platform if specified
    if args.platform:
        all_conversations = [c for c in all_conversations if c.get("platform") == args.platform]

    print(f"Found {len(all_conversations)} conversations to process")

    # Load to mem0
    print("\nLoading to mem0...")
    total_messages, total_memories = load_to_mem0(
        all_conversations,
        client,
        user_id=args.user_id
    )

    print("\n" + "=" * 60)
    print(f"Summary:")
    print(f"  Conversations processed: {len(all_conversations)}")
    print(f"  Total messages: {total_messages}")
    print(f"  Memories added to mem0: {total_memories}")
    print("=" * 60)


if __name__ == "__main__":
    main()
