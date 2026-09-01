import { Fragment, type ReactNode } from "react";

/**
 * Minimal Markdown renderer for model-authored memos and reports.
 *
 * Deliberately not a full parser and deliberately not `dangerouslySetInnerHTML`:
 * this content is generated text, so it is rendered as React elements with no
 * HTML passthrough. It covers what the report templates actually emit —
 * headings, bullets, bold, italic and paragraphs — and shows anything else
 * verbatim rather than swallowing it.
 */

function inline(text: string, keyPrefix: string): ReactNode[] {
  const nodes: ReactNode[] = [];
  // Split on bold first so `**a *b* c**` keeps its inner emphasis.
  text.split("**").forEach((chunk, boldIndex) => {
    const content =
      boldIndex % 2 === 1 ? (
        <strong className="font-semibold text-zinc-900">{emphasis(chunk, `${keyPrefix}-b${boldIndex}`)}</strong>
      ) : (
        emphasis(chunk, `${keyPrefix}-p${boldIndex}`)
      );
    nodes.push(<Fragment key={`${keyPrefix}-${boldIndex}`}>{content}</Fragment>);
  });
  return nodes;
}

function emphasis(text: string, keyPrefix: string): ReactNode[] {
  return text.split("*").map((chunk, index) =>
    index % 2 === 1 ? (
      <em key={`${keyPrefix}-${index}`} className="italic">
        {chunk}
      </em>
    ) : (
      <Fragment key={`${keyPrefix}-${index}`}>{chunk}</Fragment>
    ),
  );
}

type Block =
  | { kind: "heading"; level: 1 | 2 | 3; text: string }
  | { kind: "list"; items: string[] }
  | { kind: "paragraph"; text: string };

function parse(source: string): Block[] {
  const blocks: Block[] = [];
  let list: string[] | null = null;

  const flushList = () => {
    if (list && list.length > 0) {
      blocks.push({ kind: "list", items: list });
    }
    list = null;
  };

  for (const raw of source.split("\n")) {
    const line = raw.trim();
    if (!line) {
      flushList();
      continue;
    }

    const heading = /^(#{1,3})\s+(.*)$/.exec(line);
    if (heading) {
      flushList();
      blocks.push({
        kind: "heading",
        level: heading[1].length as 1 | 2 | 3,
        text: heading[2],
      });
      continue;
    }

    const bullet = /^[-*+]\s+(.*)$/.exec(line);
    if (bullet) {
      list = list ?? [];
      list.push(bullet[1]);
      continue;
    }

    flushList();
    blocks.push({ kind: "paragraph", text: line });
  }
  flushList();
  return blocks;
}

const HEADING_CLASS = {
  1: "mt-4 text-base font-semibold text-zinc-900 first:mt-0",
  2: "mt-4 border-b border-hairline pb-1 text-sm font-semibold text-zinc-900 first:mt-0",
  3: "mt-3 text-[13px] font-semibold text-zinc-800 first:mt-0",
} as const;

export function Markdown({ source, className = "" }: { source: string; className?: string }) {
  const blocks = parse(source);

  return (
    <div className={`text-sm leading-6 text-zinc-700 ${className}`}>
      {blocks.map((block, index) => {
        if (block.kind === "heading") {
          const Tag = (["h3", "h4", "h5"] as const)[block.level - 1];
          return (
            <Tag key={index} className={HEADING_CLASS[block.level]}>
              {inline(block.text, `h${index}`)}
            </Tag>
          );
        }
        if (block.kind === "list") {
          return (
            <ul key={index} className="my-2 list-disc space-y-1 pl-5">
              {block.items.map((item, itemIndex) => (
                <li key={itemIndex}>{inline(item, `l${index}-${itemIndex}`)}</li>
              ))}
            </ul>
          );
        }
        return (
          <p key={index} className="my-2">
            {inline(block.text, `p${index}`)}
          </p>
        );
      })}
    </div>
  );
}
