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
    nodeBg: "#74b9ff",
    nodeText: "#1a1a2e",
    actorBg: "#fab1a0",
    weBg: "#55efc4",
    edgeLine: "#636e72",
    edgeText: "#555555",
    edgeLabelBg: "#ffffff",
    subsum: "#6c5ce7",
    subsumBy: "#a29bfe",
    coref: "#b2bec3",
  },
  dark: {
    nodeBg: "#89b4fa",
    nodeText: "#1e1e2e",
    actorBg: "#f38ba8",
    weBg: "#a6e3a1",
    edgeLine: "#9399b2",
    edgeText: "#cdd6f4",
    edgeLabelBg: "#1e1e2e",
    subsum: "#cba6f7",
    subsumBy: "#b4befe",
    coref: "#585b70",
  },
};

function buildStyle(t: Theme): StylesheetJson {
  return [
    {
      selector: "node",
      style: {
        label: "data(label)",
        "font-size": "11px",
        "text-valign": "center",
        "text-halign": "center",
        "background-color": t.nodeBg,
        color: t.nodeText,
        "text-wrap": "wrap",
        "text-max-width": "100px",
        width: "label",
        height: "label",
        padding: "8px",
        shape: "round-rectangle",
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
        color: t.edgeText,
        "curve-style": "bezier",
        "target-arrow-shape": "triangle",
        "arrow-scale": 1.2,
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
  { label: "DATA", light: "#2980b9", dark: "#89b4fa" },
  { label: "ACTOR", light: "#c0392b", dark: "#f38ba8" },
  { label: "we", light: "#27ae60", dark: "#a6e3a1" },
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
      <div className="absolute left-2 top-2 z-10 flex gap-3 rounded bg-white/80 px-2 py-1 text-xs dark:bg-zinc-900/80">
        {LEGEND.map((item) => (
          <LegendDot key={item.label} {...item} />
        ))}
      </div>
      <div ref={containerRef} className="h-full w-full rounded bg-[#fafafa] dark:bg-[#1e1e2e]" />
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
    <div className="flex h-full items-center justify-center p-4 text-center text-sm text-zinc-400 dark:text-zinc-500">
      {children}
    </div>
  );
}
