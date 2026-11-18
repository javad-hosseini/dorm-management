import * as React from "react"
import { withMdxcn } from "@/registry/default/mdx/mdx"
import * as mdxcn from "@/registry/default"

export type MDXComponents = Record<string, React.ComponentType<any>>

/**
 * Register the mdxcn parents once in mdx-components.tsx.
 * In the MDX file, wrap markdown children in the parent tag.
 * Plain markdown elements (> [!WARNING], quotes, console sessions)
 * are also upgraded to frames automatically via withMdxcn.
 */
export function useMDXComponents(components: MDXComponents = {}): MDXComponents {
  return withMdxcn({
    ...components,

    // Frame Primitives
    Graph: mdxcn.Graph,
    GraphFrameProvider: mdxcn.GraphFrameProvider,
    Head: mdxcn.Head,
    Row: mdxcn.Row,
    Cell: mdxcn.Cell,
    Foot: mdxcn.Foot,

    // Content Frames & Asides
    Callout: mdxcn.Callout,
    Quote: mdxcn.Quote,
    Steps: mdxcn.Steps,
    Step: mdxcn.Step,
    Terminal: mdxcn.Terminal,
    Changelog: mdxcn.Changelog,
    Change: mdxcn.Change,
    Annotate: mdxcn.Annotate,
    Decision: mdxcn.Decision,
    Chat: mdxcn.Chat,
    Env: mdxcn.Env,
    Endpoint: mdxcn.Endpoint,
    Keys: mdxcn.Keys,
    Faq: mdxcn.Faq,

    // Chooser Graphs & Diagrams
    GraphSpark: mdxcn.GraphSpark,
    GraphPlot: mdxcn.GraphPlot,
    GraphMeter: mdxcn.GraphMeter,
    GraphStack: mdxcn.GraphStack,
    GraphWaffle: mdxcn.GraphWaffle,
    GraphUptime: mdxcn.GraphUptime,
    GraphBullet: mdxcn.GraphBullet,
    GraphSlope: mdxcn.GraphSlope,
    GraphRank: mdxcn.GraphRank,
    GraphKpi: mdxcn.GraphKpi,
    GraphStat: mdxcn.GraphStat,
    GraphTimer: mdxcn.GraphTimer,
    GraphCountdown: mdxcn.GraphCountdown,
    GraphFlow: mdxcn.GraphFlow,
    GraphTimeline: mdxcn.GraphTimeline,
    GraphCompare: mdxcn.GraphCompare,
    GraphMatrix: mdxcn.GraphMatrix,
    GraphSheet: mdxcn.GraphSheet,
    GraphCheck: mdxcn.GraphCheck,
    GraphDiff: mdxcn.GraphDiff,
    GraphGantt: mdxcn.GraphGantt,
    GraphTable: mdxcn.GraphTable,
    GraphBars: mdxcn.GraphBars,
    GraphCells: mdxcn.GraphCells,
    GraphTree: mdxcn.GraphTree,
    GraphFunnel: mdxcn.GraphFunnel,
    GraphBoard: mdxcn.GraphBoard,
    GraphActivity: mdxcn.GraphActivity,
    GraphHeatmap: mdxcn.GraphHeatmap,
    GraphCalendar: mdxcn.GraphCalendar,
    GraphWaterfall: mdxcn.GraphWaterfall,
    GraphScore: mdxcn.GraphScore,
    GraphSpec: mdxcn.GraphSpec,
  })
}
