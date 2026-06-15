"""Jukola relay insights generator.

Parses an IOF-style relay results XML and renders one static HTML page per
team plus an index. Pure stdlib, no LLM — the analysis layer produces plain
data structures so an LLM summarizer can be glued on later.
"""
