// 分块管理（CONTEXT.md：可独立索引与引证的结构感知片段；来源元数据 = 页面引用 + 标题链）。
import { useQuery } from "@tanstack/react-query";
import { createFileRoute, Link, useNavigate } from "@tanstack/react-router";
import { Boxes, ChevronRight } from "lucide-react";
import { useEffect, useMemo, useRef, useState, type ReactNode, type RefObject } from "react";
import { AdminPageHeader } from "../../components/admin-page-header";
import { Badge } from "../../components/ui/badge";
import { badgeSem } from "../../lib/status";
import { Button } from "../../components/ui/button";
import { Card, CardContent } from "../../components/ui/card";
import { Skeleton } from "../../components/ui/skeleton";
import { DataTable } from "../../components/data-table";
import type { ColumnDef } from "@tanstack/react-table";
import type { AppTableFeatures } from "../../lib/table";
import type { Chunk } from "../../lib/types";
import {
  chunksQueryOptions,
  documentsQueryOptions,
  knowledgeBasesQueryOptions,
} from "../../lib/queries";
import { formatDateTime } from "../../lib/format";

const Route = createFileRoute("/admin/knowledge/$kbId/docs/$docId")({});

export function KnowledgeChunksScreen() {
  const { docId, kbId } = Route.useParams();
  const navigate = useNavigate();
  const { data: chunks = [], isError, isPending, refetch } = useQuery(chunksQueryOptions(docId));
  // 分块端点不携带文档/知识库名称，从相邻列表查询联表取展示名（同缓存，零额外请求）。
  const { data: docs = [] } = useQuery(documentsQueryOptions(kbId));
  const { data: kbs = [] } = useQuery(knowledgeBasesQueryOptions());
  const docTitle = docs.find((d) => d.id === docId)?.title;
  const kbName = kbs.find((k) => k.id === kbId)?.name;
  const [showPreview, setShowPreview] = useState(false);

  const columns = useMemo<ColumnDef<AppTableFeatures, Chunk>[]>(
    () => [
      {
        accessorKey: "content",
        header: "内容",
        cell: (info) => {
          const chunk = info.row.original;
          return (
            <div>
              {chunk.pageRef || chunk.headings?.length ? (
                <div className="mb-1 flex flex-wrap gap-1">
                  {chunk.headings?.map((h) => (
                    <Badge key={h} {...badgeSem("neutral")}>
                      {h}
                    </Badge>
                  ))}
                  {chunk.pageRef ? <Badge {...badgeSem("neutral")}>{chunk.pageRef}</Badge> : null}
                </div>
              ) : null}
              <span className="line-clamp-3 font-medium text-ink" title={chunk.content}>
                {chunk.content}
              </span>
            </div>
          );
        },
      },
      {
        accessorKey: "tokenCount",
        header: "Token",
        cell: (info) => <span className="tabular-nums">{info.getValue<number>()}</span>,
      },
      {
        accessorKey: "createdAt",
        header: "更新时间",
        cell: (info) => (
          <span className="whitespace-nowrap">{formatDateTime(info.getValue<string>())}</span>
        ),
      },
    ],
    [],
  );

  return (
    <div>
      <nav
        aria-label="面包屑"
        className="mb-3 flex items-center gap-1.5 text-caption text-muted-foreground"
      >
        <Link
          to="/admin/knowledge"
          className="rounded-sm font-medium text-accent-ink outline-none hover:underline focus-visible:ring-2 focus-visible:ring-ring"
        >
          知识库管理
        </Link>
        <ChevronRight className="size-3.5" aria-hidden />
        <Link
          to="/admin/knowledge/$kbId"
          params={{ kbId }}
          className="min-w-0 truncate rounded-sm font-medium text-accent-ink outline-none hover:underline focus-visible:ring-2 focus-visible:ring-ring"
        >
          {kbName ?? "知识库"}
        </Link>
        <ChevronRight className="size-3.5" aria-hidden />
        <span className="min-w-0 truncate text-ink">{docTitle ?? "文档分块"}</span>
      </nav>
      <AdminPageHeader
        icon={Boxes}
        title="分块管理"
        description={docTitle ? `${docTitle}（知识库: ${kbName ?? "—"}）` : "文档分块"}
        actions={
          <>
            <Button
              variant="secondary"
              onClick={() => navigate({ to: "/admin/knowledge/$kbId", params: { kbId } })}
            >
              返回文档
            </Button>
            <Button variant="secondary" onClick={() => setShowPreview((v) => !v)}>
              {showPreview ? "隐藏预览" : "预览文档"}
            </Button>
          </>
        }
      />

      {showPreview && docTitle ? (
        <Card className="mb-4">
          <CardContent className="py-5">
            <DocumentPreview
              documentId={docId}
              format={docs.find((d) => d.id === docId)?.format ?? ""}
              title={docTitle}
            />
          </CardContent>
        </Card>
      ) : null}

      <div className="mb-3 flex items-center gap-3">
        <span className="text-caption text-muted-foreground">共 {chunks.length} 个分块</span>
      </div>
      <DataTable
        ariaLabel="分块列表"
        columns={columns}
        data={chunks}
        loading={isPending}
        error={isError}
        onRetry={() => void refetch()}
        emptyTitle="暂无分块"
        emptyDescription="文档完成摄取后，分块会显示在这里，并作为回答的证据来源。"
      />
    </div>
  );
}

/* ---------- 文档预览（内联于本屏；：pdfjs PDF / docx-preview / 原生 md/txt/图片；xlsx/pptx 不内嵌） ---------- */

const UNSAFE_PREVIEW = ["pptx", "xlsx"];

function DocumentPreview({
  documentId,
  format,
  title,
}: {
  documentId: string;
  format: string;
  title: string;
}) {
  const ref = useRef<HTMLDivElement>(null);
  const [status, setStatus] = useState<"loading" | "ready" | "error" | "unsupported">("loading");
  const [text, setText] = useState("");
  const [imageUrl, setImageUrl] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    let createdUrl: string | null = null;
    const ext = format.startsWith(".") ? format : `.${format}`;
    if (UNSAFE_PREVIEW.includes(ext.slice(1))) {
      setStatus("unsupported");
      return;
    }
    setStatus("loading");
    fetch(`/api/admin/documents/${documentId}/content`, { credentials: "same-origin" })
      .then(async (response) => {
        if (!response.ok) throw new Error("content unavailable");
        if (cancelled) return;
        if (ext === ".pdf") {
          await renderPdf(ref, response, setStatus, title);
        } else if (ext === ".docx") {
          await renderDocx(ref, response, setStatus);
        } else if (ext === ".md" || ext === ".txt") {
          const text = await response.text();
          if (cancelled) return;
          setText(text);
          setStatus("ready");
        } else if (ext === ".png" || ext === ".jpg" || ext === ".jpeg") {
          const url = URL.createObjectURL(await response.blob());
          if (cancelled) {
            URL.revokeObjectURL(url);
            return;
          }
          createdUrl = url;
          setImageUrl(url);
          setStatus("ready");
        } else {
          setStatus("error");
        }
      })
      .catch(() => !cancelled && setStatus("error"));
    return () => {
      cancelled = true;
      if (createdUrl) URL.revokeObjectURL(createdUrl);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [documentId, format]);

  return (
    <div aria-label={`文档预览：${title}`}>
      {status === "loading" ? (
        <Skeleton className="h-[360px] w-full" />
      ) : status === "unsupported" ? (
        <PreviewMessage>该格式（PPTX/XLSX）v1 暂不支持内嵌预览。</PreviewMessage>
      ) : status === "error" ? (
        <PreviewMessage>文档内容暂不可用（可能尚未完成摄取）。</PreviewMessage>
      ) : (
        <>
          <div ref={ref} className="overflow-x-auto" />
          {text ? (
            <pre className="max-h-96 overflow-auto rounded-md bg-panel p-4 font-mono text-body-sm leading-relaxed whitespace-pre-wrap text-body">
              {text}
            </pre>
          ) : null}
          {imageUrl ? (
            <img src={imageUrl} alt={title} className="max-h-96 max-w-full rounded-md" />
          ) : null}
        </>
      )}
    </div>
  );
}

function PreviewMessage({ children }: { children: ReactNode }) {
  return (
    <div className="grid place-items-center rounded-md border border-dashed border-border px-6 py-12 text-body-sm text-muted-foreground">
      {children}
    </div>
  );
}

async function renderPdf(
  ref: RefObject<HTMLDivElement | null>,
  response: Response,
  setStatus: (s: "loading" | "ready" | "error") => void,
  title: string,
): Promise<void> {
  if (!ref.current) return;
  const { getDocument, GlobalWorkerOptions } = await import("pdfjs-dist");
  GlobalWorkerOptions.workerSrc = new URL(
    "pdfjs-dist/build/pdf.worker.min.mjs",
    import.meta.url,
  ).toString();
  const data = await response.arrayBuffer();
  const pdf = await getDocument({ data }).promise;
  const page = await pdf.getPage(1);
  const viewport = page.getViewport({ scale: 1.5 });
  const canvas = document.createElement("canvas");
  canvas.width = viewport.width;
  canvas.height = viewport.height;
  canvas.setAttribute("aria-label", `${title} 第 1 页`);
  await page.render({ canvas, viewport }).promise;
  ref.current.appendChild(canvas);
  setStatus("ready");
}

async function renderDocx(
  ref: RefObject<HTMLDivElement | null>,
  response: Response,
  setStatus: (s: "loading" | "ready" | "error") => void,
): Promise<void> {
  const blob = await response.blob();
  if (ref.current) {
    const { renderAsync } = await import("docx-preview");
    await renderAsync(blob, ref.current);
  }
  setStatus("ready");
}
