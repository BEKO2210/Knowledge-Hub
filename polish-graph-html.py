#!/usr/bin/env python3
"""Post-mapping polish for graphify's graph.html.

graphify regenerates graph.html on every nightly map, so viewer tweaks cannot
live in the file itself -- they would be overwritten. This script re-applies
them after each map. It is idempotent (a marker guards against double-patching)
and purely additive (it never removes graphify's own markup).

Two fixes, both requested by the operator:
  1. Mobile: long file names / labels broke the layout because the panel and
     lists used white-space:nowrap + ellipsis. Add a viewport meta and CSS that
     wraps long text and makes the side panel usable on a phone.
  2. Click-to-read: the info panel showed only label/type/community/source. The
     node's full detail text (its vis `title`) is already embedded but was never
     surfaced. Add it to the panel as a scrollable, wrapping "Details" block.

Usage: polish-graph-html.py <graph.html> [<graph.html> ...]
       polish-graph-html.py --all      # every enabled project's graph.html
"""

import sys
import pathlib

MARKER = "<!-- ee-polish v1 -->"

VIEWPORT = '<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">'

CSS = """
<style>/* ee-polish: readable content + mobile wrapping */
#info-content .field { white-space: normal !important; overflow-wrap: anywhere; word-break: break-word; }
#info-content .field.ee-source { font-family: ui-monospace, SFMono-Regular, Menlo, monospace; font-size: 12px; color: #bcd; }
.neighbor-link { white-space: normal !important; overflow: visible !important; text-overflow: clip !important; overflow-wrap: anywhere; }
.search-item { white-space: normal !important; overflow: visible !important; text-overflow: clip !important; overflow-wrap: anywhere; }
.legend-label { white-space: normal !important; overflow: visible !important; text-overflow: clip !important; overflow-wrap: anywhere; }
#ee-details { margin-top: 8px; max-height: 40vh; overflow-y: auto; white-space: pre-wrap; overflow-wrap: anywhere;
  font-size: 12.5px; line-height: 1.55; color: #d6d6e0; background: rgba(255,255,255,0.03);
  border-left: 3px solid #4a4a6a; border-radius: 4px; padding: 8px 10px; }
#ee-details:empty { display: none; }
@media (max-width: 640px) {
  #info-panel { min-height: 0 !important; padding: 10px !important; }
  #ee-details { max-height: 32vh; }
  #info-content { font-size: 14px !important; }
}
</style>
"""

# Injected AFTER graphify's own script. graphify does NOT carry the node content
# (the `rationale`) into the HTML -- only the label. So we read it from the
# sibling graph.json and inject an id->detail map, then show it on click. This
# is what makes "click a node and read its content" actually work.
JS_TEMPLATE = """
<script>/* ee-polish: node content on click, from graph.json */
window.EE_NODE_DETAILS = __DETAILS_JSON__;
(function () {
  function findNetwork() { try { return network; } catch (e) {} return window.network || null; }
  function render(nodeId) {
    var host = document.getElementById('info-content');
    if (!host) return;
    var box = document.getElementById('ee-details');
    if (!box) { box = document.createElement('div'); box.id = 'ee-details'; host.appendChild(box); }
    var d = window.EE_NODE_DETAILS[nodeId];
    var parts = [];
    if (d) {
      if (d.rationale) parts.push(d.rationale);
      if (d.source_url && d.source_url !== 'None') parts.push('\\n\\nQuelle: ' + d.source_url);
      if (d.source_location && d.source_location !== 'None') parts.push('\\nStelle: ' + d.source_location);
    }
    box.textContent = parts.join('');
  }
  function wire() {
    var net = findNetwork();
    if (!net) { setTimeout(wire, 300); return; }
    net.on('selectNode', function (p) { if (p.nodes && p.nodes.length) render(p.nodes[0]); });
    net.on('click', function (p) { if (p.nodes && p.nodes.length) render(p.nodes[0]); });
  }
  if (document.readyState !== 'loading') wire();
  else document.addEventListener('DOMContentLoaded', wire);
})();
</script>
"""


def build_details_json(graph_json: pathlib.Path) -> str:
    """Extract an id -> {rationale, source_url, source_location} map from graph.json."""
    import json

    if not graph_json.exists():
        return "{}"
    try:
        data = json.loads(graph_json.read_text(encoding="utf-8"))
    except Exception:
        return "{}"
    out = {}
    for n in data.get("nodes", []):
        nid = n.get("id")
        if not nid:
            continue
        rec = {}
        for k in ("rationale", "source_url", "source_location"):
            v = n.get(k)
            if v and v != "None":
                rec[k] = str(v)[:4000]
        if rec:
            out[nid] = rec
    return json.dumps(out, ensure_ascii=False)


def polish(path: pathlib.Path) -> str:
    html = path.read_text(encoding="utf-8")
    if MARKER in html:
        return "already polished"

    original = html
    details = build_details_json(path.parent / "graph.json")
    JS = JS_TEMPLATE.replace("__DETAILS_JSON__", details)

    # 1. viewport meta
    if 'name="viewport"' not in html:
        if "<head>" in html:
            html = html.replace("<head>", "<head>\n" + VIEWPORT, 1)
        else:
            html = VIEWPORT + "\n" + html

    # 2. CSS + marker: just before </head> (or prepend if no head)
    inject_head = MARKER + CSS
    if "</head>" in html:
        html = html.replace("</head>", inject_head + "\n</head>", 1)
    else:
        html = inject_head + html

    # 3. JS: just before </body> (or append)
    if "</body>" in html:
        html = html.replace("</body>", JS + "\n</body>", 1)
    else:
        html = html + JS

    if html == original:
        return "no change (unexpected structure)"

    path.write_text(html, encoding="utf-8")
    return "polished"


def enabled_graph_htmls() -> list[pathlib.Path]:
    import yaml  # type: ignore

    cfg = yaml.safe_load((pathlib.Path.home() / ".config/knowledge-mcp/config.yaml").read_text())
    out = []
    for entry in cfg.get("mapping", {}).get("projects", []):
        if not entry.get("enabled"):
            continue
        p = pathlib.Path(entry["path"].replace("~", str(pathlib.Path.home())))
        g = p / "graphify-out" / "graph.html"
        if g.exists():
            out.append(g)
    return out


def served_graph_htmls() -> list[pathlib.Path]:
    """The copies the viewer actually serves: <knowledge_root>/*/graphify-out/graph.html."""
    import yaml  # type: ignore

    cfg = yaml.safe_load((pathlib.Path.home() / ".config/knowledge-mcp/config.yaml").read_text())
    root = pathlib.Path(cfg["paths"]["knowledge_root"].replace("~", str(pathlib.Path.home())))
    return sorted(root.glob("*/graphify-out/graph.html"))


def main() -> int:
    args = sys.argv[1:]
    if args == ["--all"]:
        targets = enabled_graph_htmls()
    elif args == ["--served"]:
        # The copies the viewer serves from knowledge_root. This is what makes the
        # changes visible in the web UI, not the source graphify-out.
        targets = served_graph_htmls()
    else:
        targets = [pathlib.Path(a) for a in args]
    if not targets:
        print("usage: polish-graph-html.py <graph.html>... | --all", file=sys.stderr)
        return 2
    for t in targets:
        if not t.exists():
            print(f"  skip {t} (missing)")
            continue
        print(f"  {t}: {polish(t)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
