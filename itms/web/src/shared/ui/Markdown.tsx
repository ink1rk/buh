import { Fragment, type ReactNode } from "react";

/**
 * Небольшой отрисовщик Markdown без innerHTML: заголовки, списки, код, цитаты,
 * жирный/курсив/код и ссылки. Внешняя библиотека не нужна, а XSS невозможен,
 * потому что текст всегда попадает в React-узлы.
 */

const INLINE = /(\*\*[^*]+\*\*|\*[^*]+\*|`[^`]+`|\[[^\]]+\]\([^)\s]+\))/g;

function renderInline(text: string, keyPrefix: string): ReactNode[] {
  return text.split(INLINE).map((chunk, index) => {
    const key = `${keyPrefix}-${index}`;
    if (chunk.startsWith("**") && chunk.endsWith("**")) {
      return <strong key={key}>{chunk.slice(2, -2)}</strong>;
    }
    if (chunk.startsWith("*") && chunk.endsWith("*") && chunk.length > 2) {
      return <em key={key}>{chunk.slice(1, -1)}</em>;
    }
    if (chunk.startsWith("`") && chunk.endsWith("`")) {
      return (
        <code key={key} className="rounded surface-muted px-1 font-mono text-xs">
          {chunk.slice(1, -1)}
        </code>
      );
    }
    const link = /^\[([^\]]+)\]\(([^)\s]+)\)$/.exec(chunk);
    if (link) {
      const href = link[2];
      const safe = /^(https?:|\/)/i.test(href) ? href : "#";
      return (
        <a key={key} href={safe} target="_blank" rel="noreferrer" className="text-accent hover:underline">
          {link[1]}
        </a>
      );
    }
    return <Fragment key={key}>{chunk}</Fragment>;
  });
}

const HEADING_CLASS = [
  "text-base font-semibold mt-4 mb-1.5",
  "text-sm font-semibold mt-3 mb-1.5",
  "text-sm font-medium mt-3 mb-1",
];

export function Markdown({ source }: { source: string }) {
  if (!source.trim()) return null;

  const blocks: ReactNode[] = [];
  const lines = source.replace(/\r\n/g, "\n").split("\n");
  let index = 0;
  let key = 0;

  while (index < lines.length) {
    const line = lines[index];

    if (!line.trim()) {
      index += 1;
      continue;
    }

    if (line.startsWith("```")) {
      const code: string[] = [];
      index += 1;
      while (index < lines.length && !lines[index].startsWith("```")) {
        code.push(lines[index]);
        index += 1;
      }
      index += 1;
      blocks.push(
        <pre
          key={key++}
          className="my-2 overflow-x-auto rounded surface-muted p-2.5 font-mono text-xs"
        >
          <code>{code.join("\n")}</code>
        </pre>,
      );
      continue;
    }

    const heading = /^(#{1,3})\s+(.*)$/.exec(line);
    if (heading) {
      const level = heading[1].length;
      const Tag = `h${level + 1}` as "h2" | "h3" | "h4";
      blocks.push(
        <Tag key={key++} className={HEADING_CLASS[level - 1]}>
          {renderInline(heading[2], `h${key}`)}
        </Tag>,
      );
      index += 1;
      continue;
    }

    if (/^\s*[-*]\s+/.test(line)) {
      const items: string[] = [];
      while (index < lines.length && /^\s*[-*]\s+/.test(lines[index])) {
        items.push(lines[index].replace(/^\s*[-*]\s+/, ""));
        index += 1;
      }
      blocks.push(
        <ul key={key++} className="my-1.5 list-disc pl-5">
          {items.map((item, itemIndex) => (
            <li key={itemIndex} className="leading-6">
              {renderInline(item, `li${key}-${itemIndex}`)}
            </li>
          ))}
        </ul>,
      );
      continue;
    }

    if (/^\s*\d+[.)]\s+/.test(line)) {
      const items: string[] = [];
      while (index < lines.length && /^\s*\d+[.)]\s+/.test(lines[index])) {
        items.push(lines[index].replace(/^\s*\d+[.)]\s+/, ""));
        index += 1;
      }
      blocks.push(
        <ol key={key++} className="my-1.5 list-decimal pl-5">
          {items.map((item, itemIndex) => (
            <li key={itemIndex} className="leading-6">
              {renderInline(item, `ol${key}-${itemIndex}`)}
            </li>
          ))}
        </ol>,
      );
      continue;
    }

    if (line.startsWith("> ")) {
      blocks.push(
        <blockquote key={key++} className="my-2 border-l-2 border-app pl-3 text-muted">
          {renderInline(line.slice(2), `q${key}`)}
        </blockquote>,
      );
      index += 1;
      continue;
    }

    const paragraph: string[] = [];
    while (index < lines.length && lines[index].trim() && !/^(#{1,3}\s|```|>\s|\s*[-*]\s|\s*\d+[.)]\s)/.test(lines[index])) {
      paragraph.push(lines[index]);
      index += 1;
    }
    blocks.push(
      <p key={key++} className="my-1.5 leading-6">
        {renderInline(paragraph.join(" "), `p${key}`)}
      </p>,
    );
  }

  return <div className="text-sm">{blocks}</div>;
}
