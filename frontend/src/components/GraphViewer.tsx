import cytoscape from "cytoscape";
import type { StylesheetJson } from "cytoscape";
import { useEffect, useRef } from "react";

import { useGraph } from "../hooks/queries";

type Theme = {
  nodeBg: string;
  nodeText: string;
  actorBg: string;
  weBg: string;
  edgeLine: string;
  edgeText: string;
  edgeLabelBg: string;
  subsum: string;
  subsumBy: string;
  coref: string;
};

const THEMES: Record<"light" | "dark", Theme> = {
  light: {
    nodeBg: "#b9d2ce",
    nodeText: "#17202a",
    actorBg: "#dfc0af",
    weBg: "#d5d2a6",
    edgeLine: "#64748b",
    edgeText: "#475569",
    edgeLabelBg: "#ffffff",
    subsum: "#766b8f",
    subsumBy: "#8a7f6a",
    coref: "#94a3b8",
  },
  dark: {
    nodeBg: "#2f6f69",
    nodeText: "#f8fafc",
    actorBg: "#8c5145",
    weBg: "#66744a",
    edgeLine: "#64748b",
    edgeText: "#cbd5e1",
    edgeLabelBg: "#111827",
    subsum: "#8b7aaa",
    subsumBy: "#9a8b70",
    coref: "#475569",
  },
};

function buildStyle(t: Theme): StylesheetJson {
  return [
    {
      selector: "node",
      style: {
        label: "data(label)",
        "font-size": "11px",
        "font-family": "Source Sans 3 Variable, sans-serif",
        "text-valign": "center",
        "text-halign": "center",
        "background-color": t.nodeBg,
        color: t.nodeText,
        "text-wrap": "wrap",
        "text-max-width": "100px",
        width: "label",
        height: "label",
        padding: "8px",
        shape: "rectangle",
      },
    },
    {
      selector: 'node[type = "ACTOR"]',
      style: { "background-color": t.actorBg, shape: "ellipse" },
    },
    {
      selector: 'node[id = "we"]',
      style: { "background-color": t.weBg, "font-weight": "bold", shape: "diamond" },
    },
    {
      selector: "edge",
      style: {
        label: "data(label)",
        "font-size": "10px",
        "font-family": "Source Sans 3 Variable, sans-serif",
        color: t.edgeText,
        "curve-style": "bezier",
        "target-arrow-shape": "triangle",
        "arrow-scale": 0.9,
        "line-color": t.edgeLine,
        "target-arrow-color": t.edgeLine,
        "text-rotation": "autorotate",
        "text-background-color": t.edgeLabelBg,
        "text-background-opacity": 0.8,
        "text-background-padding": "2px",
      },
    },
    {
      selector: 'edge[label = "SUBSUM"]',
      style: { "line-style": "dashed", "line-color": t.subsum, "target-arrow-color": t.subsum },
    },
    {
      selector: 'edge[label = "SUBSUM_BY"]',
      style: { "line-style": "dashed", "line-color": t.subsumBy, "target-arrow-color": t.subsumBy },
    },
    {
      selector: 'edge[label = "COREF"]',
      style: { "line-style": "dotted", "line-color": t.coref, "target-arrow-color": t.coref },
    },
  ];
}

const LEGEND = [
  { label: "DATA", light: "#6b9690", dark: "#2f6f69" },
  { label: "ACTOR", light: "#b5775f", dark: "#8c5145" },
  { label: "we", light: "#8d8a55", dark: "#66744a" },
];

export function GraphViewer({ policyId }: { policyId: string }) {
  const { data, isLoading, isError } = useGraph(policyId);
  const containerRef = useRef<HTMLDivElement>(null);
  const cyRef = useRef<cytoscape.Core | null>(null);

  useEffect(() => {
    if (!containerRef.current || !data) return;

    const mq = window.matchMedia("(prefers-color-scheme: dark)");
    const cy = cytoscape({
      container: containerRef.current,
      elements: data.elements,
      style: buildStyle(mq.matches ? THEMES.dark : THEMES.light),
      layout: {
        name: "cose",
        animate: false,
        randomize: true,
        nodeRepulsion: () => 8000,
        idealEdgeLength: () => 100,
        edgeElasticity: () => 200,
      },
    });
    cyRef.current = cy;

    const onThemeChange = (e: MediaQueryListEvent) =>
      cy.style(buildStyle(e.matches ? THEMES.dark : THEMES.light)).update();
    mq.addEventListener("change", onThemeChange);

    return () => {
      mq.removeEventListener("change", onThemeChange);
      cy.destroy();
      cyRef.current = null;
    };
  }, [data]);

  if (isLoading) {
    return <Centered>Loading graph…</Centered>;
  }
  if (isError || !data) {
    return <Centered>No graph generated yet. Use the Generate button on the policy row.</Centered>;
  }

  return (
    <div className="relative h-full w-full">
      <div className="absolute left-3 top-3 z-10 flex gap-3 rounded border border-slate-300 bg-white px-2.5 py-1.5 text-xs dark:border-slate-700 dark:bg-slate-900">
        {LEGEND.map((item) => (
          <LegendDot key={item.label} {...item} />
        ))}
      </div>
      <div ref={containerRef} className="h-full w-full bg-slate-50 dark:bg-slate-900" />
    </div>
  );
}

function LegendDot({ label, light, dark }: { label: string; light: string; dark: string }) {
  const isDark = window.matchMedia("(prefers-color-scheme: dark)").matches;
  return (
    <span className="flex items-center gap-1">
      <span
        className="inline-block h-2.5 w-2.5 rounded-full"
        style={{ backgroundColor: isDark ? dark : light }}
      />
      {label}
    </span>
  );
}

function Centered({ children }: { children: React.ReactNode }) {
  return (
    <div className="flex h-full items-center justify-center p-4 text-center text-sm text-slate-400 dark:text-slate-500">
      {children}
    </div>
  );
}
