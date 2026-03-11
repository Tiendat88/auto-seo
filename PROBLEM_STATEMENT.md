# AI-role-assignment

## Backend Engineer Position - Take-Home Assessment

### Context

We're building a content generation platform that helps businesses create SEO-optimized articles at scale. One of our core features is an intelligent agent that can analyze search engine results and produce high-quality, keyword-optimized content that ranks well while still reading naturally.

### The Problem

Design and implement a backend service that generates SEO-optimized articles for a given topic. The system should be intelligent about how it approaches content creation - not just generating text, but actually understanding what's ranking on search engines and why.

### What We're Looking For

Build an agent-based system that takes a topic (like "best productivity tools for remote teams") and produces a complete, publish-ready article. The agent should:

1. Research the competitive landscape by analyzing the top 10 search results for relevant keywords
2. Identify what topics and subtopics are being covered by successful content
3. Generate a structured outline that addresses the same search intent
4. Produce a full article that follows SEO best practices without feeling robotic

### Technical Requirements

**Input Structure:**
- Topic or primary keyword
- Target word count (default 1500)
- Language preference

**Expected Output:**
- Article with proper heading hierarchy (H1, H2, H3)
- SEO metadata (title tag, meta description)
- Keyword analysis showing primary and secondary keywords used
- Structured data that can be validated programmatically
- Internal linking suggestions (3-5 relevant anchor texts with suggested target pages)
- External references (2-4 authoritative sources to cite, with context for placement)

**Architecture Considerations:**
- Use structured data models throughout (Pydantic or similar)
- Handle external API failures gracefully
- Persist generation jobs so they can be tracked and resumed
- Validate that output actually meets SEO criteria

**SERP Analysis:**
You'll need to work with search result data. You can use services like SerpAPI, DataForSEO, or ValueSERP to fetch real search results, or mock the data if you prefer. The data structure should include at minimum: rank, URL, title, and snippet for each of the top 10 results. The agent should extract common themes and topics from these results to inform the outline.

If mocking the data, structure it realistically - for example:
```json
{
  "rank": 1,
  "url": "https://example.com/productivity-tools",
  "title": "15 Best Productivity Tools for Remote Teams in 2025",
  "snippet": "Discover the top productivity tools that help remote teams collaborate..."
}
```

**Quality Bar:**
The generated articles should demonstrate actual SEO principles: primary keyword in title and introduction, proper header structure, coverage of related subtopics, and most importantly - they should read like a human wrote them, not a content mill bot.

**Linking Strategy:**
- Internal links: Identify 3-5 opportunities to link to related content (e.g., "SEO keyword research tools", "content optimization checklist"). Include the anchor text and suggested target page/topic.
- External links: Select 2-4 authoritative sources to reference (think industry reports, academic studies, or established publications). Specify where in the article each citation would add credibility.

### Bonus Points

- Job management system with status tracking (pending, running, completed, failed)
- Durability - if the process crashes after collecting SERP data, it should be able to resume
- Content quality scorer that evaluates the draft and triggers revisions
- FAQ section generated from common questions in search results
- Test coverage that validates SEO constraints

### What to Submit

A GitHub repository with:
- Complete working code
- README explaining how to run it
- At least one example showing input -> output
- Brief explanation of your design decisions
- Tests demonstrating the system works

### Time Expectation

This is a substantial assignment. We expect it will take 4-6 hours for a senior engineer. Don't feel pressured to implement every bonus feature - we'd rather see a well-architected core system than a rushed implementation with everything half-done.

### Evaluation

We'll be looking at:
- Code organization and architecture decisions
- How well the agent logic synthesizes SERP data into article structure
- Quality of the generated content (does it actually follow SEO principles?)
- Error handling and validation
- Documentation clarity

If you have questions or need clarification, feel free to reach out. We're evaluating your problem-solving approach as much as your coding ability.