import cytoscape, { type Core, type ElementDefinition, type StylesheetJson } from "cytoscape";
import fcose from "cytoscape-fcose";
import { type Ref, useEffect, useImperativeHandle, useMemo, useRef, useState } from "react";

import {
  type ColorBy,
  communityColour,
  communityRanks,
  labelledIds,
  maxMetric,
  metricOf,
  nodeRadius,
  shortTitle,
  type SizeBy,
  type Tokens,
  yearColour,
  yearRange,
} from "./encode";
import type { GraphView } from "./types";
import { useTokens } from "./useTokens";

cytoscape.use(fcose as unknown as cytoscape.Ext);

export interface GraphHandle {
  zoomIn: () => void;
  zoomOut: () => void;
  fit: () => void;
  relayout: () => void;
}

interface Props {
  view: GraphView;
  sizeBy: SizeBy;
  colorBy: ColorBy;
  communities?: readonly { id: string; rank: number }[];
  selectedId?: string | null;
  onSelect?: (id: string | null) => void;
  onOpen?: (id: string) => void;
  /** Zoom, pan and hover. The dashboard preview turns this off. */
  interactive?: boolean;
  /** How many of the largest nodes keep a permanent label. */
  labelCount?: number;
  ref?: Ref<GraphHandle>;
}

function stylesheet(t: Tokens): StylesheetJson {
  return [
    {
      selector: "node",
      style: {
        "background-color": "data(color)",
        width: "data(size)",
        height: "data(size)",
        "border-width": 2,
        "border-color": t.surface,
        label: "data(label)",
        "font-size": 11,
        "font-family": "system-ui, -apple-system, Segoe UI, sans-serif",
        color: t.ink,
        "text-valign": "bottom",
        "text-margin-y": 4,
        "text-wrap": "wrap",
        "text-max-width": "130px",
        "text-background-color": t.plane,
        "text-background-opacity": 0.8,
        "text-background-padding": "2px",
        "min-zoomed-font-size": 7,
      },
    },
    {
      selector: "node[?stub]",
      style: { "background-opacity": 0.4, "border-style": "dashed", "border-color": t.ink2 },
    },
    { selector: "node.nolabel", style: { label: "" } },
    {
      selector: "edge",
      style: {
        width: 1,
        "line-color": t.axis,
        "target-arrow-color": t.axis,
        "target-arrow-shape": "triangle",
        "arrow-scale": 0.7,
        "curve-style": "bezier",
        opacity: 0.75,
      },
    },
    { selector: ".dim", style: { opacity: 0.1 } },
    {
      selector: "edge.hl",
      style: { "line-color": t.accent, "target-arrow-color": t.accent, width: 2, opacity: 1 },
    },
    {
      selector: "node.hl",
      style: { opacity: 1, "border-color": t.ink, label: "data(label)", "z-index": 10 },
    },
    { selector: "node.focus", style: { "border-width": 4, "border-color": t.ink } },
    { selector: "node.sel", style: { "border-width": 4, "border-color": t.accent } },
  ];
}

/** Fitting a handful of nodes zooms in so far that labels become huge; cap it. */
function capZoom(cy: Core) {
  if (cy.zoom() > 1.15) {
    cy.zoom({ level: 1.15, renderedPosition: { x: cy.width() / 2, y: cy.height() / 2 } });
    cy.center();
  }
}

function prefersReducedMotion(): boolean {
  return window.matchMedia?.("(prefers-reduced-motion: reduce)").matches ?? false;
}

export function GraphCanvas({
  view,
  sizeBy,
  colorBy,
  communities,
  selectedId = null,
  onSelect,
  onOpen,
  interactive = true,
  labelCount = 12,
  ref,
}: Props) {
  const container = useRef<HTMLDivElement>(null);
  const cyRef = useRef<Core | null>(null);
  const handlers = useRef({ onSelect, onOpen });
  const tokens = useTokens();
  const [hover, setHover] = useState<{ id: string; x: number; y: number } | null>(null);

  useEffect(() => {
    handlers.current = { onSelect, onOpen };
  }, [onSelect, onOpen]);

  const byId = useMemo(() => new Map(view.nodes.map((n) => [n.id, n])), [view]);

  // Build the graph whenever the data changes.
  useEffect(() => {
    if (!container.current) return;
    const elements: ElementDefinition[] = [
      ...view.nodes.map((n) => ({ data: { id: n.id, stub: n.is_stub } })),
      ...view.edges.map((e) => ({ data: { id: `${e.source}->${e.target}`, source: e.source, target: e.target } })),
    ];
    const cy = cytoscape({
      container: container.current,
      elements,
      minZoom: 0.15,
      maxZoom: 3.5,
      wheelSensitivity: 0.25,
      userZoomingEnabled: interactive,
      userPanningEnabled: interactive,
      boxSelectionEnabled: false,
      autoungrabify: !interactive,
      style: stylesheet(tokens),
    });
    cyRef.current = cy;
    const layout = cy.layout({
      name: "fcose",
      animate: !prefersReducedMotion(),
      animationDuration: 700,
      randomize: true,
      fit: true,
      padding: 36,
      nodeRepulsion: 12000,
      idealEdgeLength: 95,
      packComponents: true,
      quality: "default",
    } as cytoscape.LayoutOptions);
    layout.on("layoutstop", () => capZoom(cy));
    layout.run();

    cy.on("tap", "node", (e) => handlers.current.onSelect?.(e.target.id()));
    cy.on("tap", (e) => {
      if (e.target === cy) handlers.current.onSelect?.(null);
    });
    cy.on("dbltap", "node", (e) => handlers.current.onOpen?.(e.target.id()));
    if (interactive) {
      cy.on("mouseover", "node", (e) => {
        const node = e.target;
        cy.elements().addClass("dim");
        node.closedNeighborhood().removeClass("dim").addClass("hl");
        const pos = node.renderedPosition();
        setHover({ id: node.id(), x: pos.x, y: pos.y - node.renderedOuterHeight() / 2 + 8 });
      });
      cy.on("mouseout", "node", () => {
        cy.elements().removeClass("dim").removeClass("hl");
        setHover(null);
      });
      cy.on("viewport", () => setHover(null));
    }
    return () => {
      cy.destroy();
      cyRef.current = null;
      setHover(null);
    };
    // `tokens` is applied by the styling effect; rebuilding on a theme change would re-run the layout.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [view, interactive]);

  // Encodings and theme: cheap to re-apply without moving nodes.
  useEffect(() => {
    const cy = cyRef.current;
    if (!cy) return;
    const ranks = communityRanks(view.nodes, communities);
    const max = maxMetric(view.nodes, sizeBy);
    const [minYear, maxYear] = yearRange(view.nodes);
    const labelled = labelledIds(view.nodes, sizeBy, labelCount);
    cy.batch(() => {
      for (const n of view.nodes) {
        const el = cy.getElementById(n.id);
        if (el.empty()) continue;
        el.data({
          size: nodeRadius(metricOf(n, sizeBy), max) * 2,
          color:
            colorBy === "community"
              ? communityColour(n.community_id, ranks, tokens)
              : yearColour(n.year, minYear, maxYear, tokens),
          label: shortTitle(n.title),
        });
        el.toggleClass("nolabel", !labelled.has(n.id));
        el.toggleClass("focus", n.id === view.focus);
      }
    });
    cy.style(stylesheet(tokens));
  }, [view, sizeBy, colorBy, communities, tokens, labelCount]);

  useEffect(() => {
    const cy = cyRef.current;
    if (!cy) return;
    cy.nodes().removeClass("sel");
    if (selectedId) cy.getElementById(selectedId).addClass("sel");
  }, [selectedId, view]);

  useImperativeHandle(
    ref,
    () => ({
      zoomIn: () => {
        const cy = cyRef.current;
        if (cy) cy.zoom({ level: cy.zoom() * 1.3, renderedPosition: { x: cy.width() / 2, y: cy.height() / 2 } });
      },
      zoomOut: () => {
        const cy = cyRef.current;
        if (cy) cy.zoom({ level: cy.zoom() / 1.3, renderedPosition: { x: cy.width() / 2, y: cy.height() / 2 } });
      },
      fit: () => {
        const cy = cyRef.current;
        if (!cy) return;
        cy.fit(undefined, 36);
        capZoom(cy);
      },
      relayout: () => {
        const cy = cyRef.current;
        if (!cy) return;
        const layout = cy.layout({
            name: "fcose",
            animate: !prefersReducedMotion(),
            randomize: true,
            fit: true,
            padding: 36,
            nodeRepulsion: 12000,
            idealEdgeLength: 95,
            packComponents: true,
          } as cytoscape.LayoutOptions);
        layout.on("layoutstop", () => capZoom(cy));
        layout.run();
      },
    }),
    [],
  );

  const hovered = hover ? byId.get(hover.id) : undefined;
  return (
    <>
      <div
        ref={container}
        className="gx-canvas"
        role="img"
        aria-label={`Citation graph with ${view.nodes.length} papers and ${view.edges.length} citations. A table view is available.`}
      />
      {hover && hovered && (
        <div className="gx-tip" style={{ left: hover.x, top: hover.y }}>
          <strong>{shortTitle(hovered.title, 80)}</strong>
          <div>
            {hovered.authors.join(", ") || "Unknown authors"}
            {hovered.year != null && ` · ${hovered.year}`}
          </div>
        </div>
      )}
    </>
  );
}
