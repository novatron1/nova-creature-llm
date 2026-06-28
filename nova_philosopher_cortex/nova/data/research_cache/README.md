# Research Cache

This directory stores cached research data for offline use.
Files here are created by research agents when web fetching is enabled.

## Structure
- Each cached result is a JSON file named by topic hash
- Cache entries include: url, fetched_at, content_preview, source_quality
- Cache TTL: 24 hours by default
