"use client";

import { createContext, useCallback, useContext, useEffect, useRef, useState } from "react";
import { BrainIcon, ChevronDownIcon } from "lucide-react";
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from "@/components/ui/collapsible";
import { cn } from "@/lib/utils";

export const ANIMATION_DURATION = 200;

const ReasoningPreviewContext = createContext(false);

export type ReasoningRootProps = React.ComponentProps<typeof Collapsible> & {
  /**
   * Whether the reasoning is currently streaming. While `true` the
   * disclosure is held open with a bottom-pinned live preview; when
   * streaming ends it returns to collapsed, and the first manual
   * toggle takes over the open/close state permanently. The live preview
   * keeps following the newest tokens while the disclosure is open during
   * streaming, even after a manual toggle, and pauses while the reader is
   * scrolled up.
   */
  streaming?: boolean;
  /** 折叠展开动画开始前调用（在手动切换及流式阶段变更时触发）。 */
  onAnimationStart?: () => void;
};

function ReasoningRoot({
  className,
  streaming,
  onAnimationStart,
  children,
  ...props
}: ReasoningRootProps) {
  const [userOpen, setUserOpen] = useState<boolean | null>(null);
  const isOpen = userOpen ?? (streaming || false);
  const isPreview = streaming === true && isOpen;

  const handleOpenChange = useCallback(
    (open: boolean) => {
      onAnimationStart?.();
      setUserOpen(open);
    },
    [onAnimationStart],
  );

  return (
    <Collapsible
      data-slot="reasoning-root"
      open={isOpen}
      onOpenChange={handleOpenChange}
      className={cn(
        "aui-reasoning-root group/reasoning-root mb-4 w-full rounded-lg border px-3 py-2",
        className,
      )}
      style={
        {
          "--animation-duration": `${ANIMATION_DURATION}ms`,
        } as React.CSSProperties
      }
      {...props}
    >
      <ReasoningPreviewContext.Provider value={isPreview}>
        {children}
      </ReasoningPreviewContext.Provider>
    </Collapsible>
  );
}

function ReasoningFade({
  side,
  className,
  ...props
}: React.ComponentProps<"div"> & { side?: "top" | "bottom" }) {
  const top = side === "top";
  return (
    <div
      data-slot="reasoning-fade"
      className={cn(
        "aui-reasoning-fade pointer-events-none absolute inset-x-0 z-10 h-8",
        top
          ? "top-0 bg-[linear-gradient(to_bottom,var(--color-background),transparent)]"
          : "bottom-0 bg-[linear-gradient(to_top,var(--color-background),transparent)]",
        "fade-in-0 animate-in",
        "animation-duration-(--animation-duration)",
        className,
      )}
      {...props}
    />
  );
}

function ReasoningTrigger({
  active,
  duration,
  className,
  ...props
}: React.ComponentProps<typeof CollapsibleTrigger> & {
  active?: boolean;
  duration?: number;
}) {
  const durationText = duration ? ` (${duration}s)` : "";

  return (
    <CollapsibleTrigger
      data-slot="reasoning-trigger"
      className={cn(
        "aui-reasoning-trigger group/trigger text-muted-foreground hover:text-foreground flex max-w-[75%] origin-left items-center gap-2 py-1.5 text-sm transition-[color,scale] active:scale-[0.98]",
        className,
      )}
      {...props}
    >
      <BrainIcon
        data-slot="reasoning-trigger-icon"
        className="aui-reasoning-trigger-icon size-4 shrink-0"
      />
      <span
        data-slot="reasoning-trigger-label"
        className={cn(
          "aui-reasoning-trigger-label-wrapper inline-block leading-none tabular-nums",
          active && "shimmer motion-reduce:animate-none",
        )}
      >
        Reasoning{durationText}
      </span>
      <ChevronDownIcon
        data-slot="reasoning-trigger-chevron"
        className={cn(
          "aui-reasoning-trigger-chevron mt-0.5 size-4 shrink-0",
          "transition-transform duration-(--animation-duration) ease-[cubic-bezier(0.32,0.72,0,1)] motion-reduce:transition-none",
          "-rotate-90",
          "group-data-open/trigger:rotate-0",
          "group-data-panel-open/trigger:rotate-0",
        )}
      />
    </CollapsibleTrigger>
  );
}

function ReasoningContent({
  className,
  children,
  ...props
}: React.ComponentProps<typeof CollapsibleContent>) {
  const isPreview = useContext(ReasoningPreviewContext);

  return (
    <CollapsibleContent
      data-slot="reasoning-content"
      className={cn(
        "aui-reasoning-content text-muted-foreground relative overflow-hidden text-sm outline-none",
        "group/collapsible-content ease-[cubic-bezier(0.32,0.72,0,1)] motion-reduce:animate-none",
        "data-closed:animate-collapsible-up",
        "data-open:animate-collapsible-down",
        "data-closed:fill-mode-forwards",
        "data-closed:pointer-events-none",
        "[--tw-duration:var(--animation-duration)]",
        className,
      )}
      {...props}
    >
      <ReasoningFade side="top" />
      {children}
      {isPreview ? <ReasoningFade /> : null}
    </CollapsibleContent>
  );
}

function ReasoningText({ className, children, ...props }: React.ComponentProps<"div">) {
  const isPreview = useContext(ReasoningPreviewContext);
  const scrollRef = useRef<HTMLDivElement>(null);
  const contentRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!isPreview) return;
    const scrollEl = scrollRef.current;
    const contentEl = contentRef.current;
    if (!scrollEl || !contentEl) return;

    let pinned = true;
    let lastScrollTop = scrollEl.scrollTop;
    let lastScrollHeight = scrollEl.scrollHeight;
    const isAtBottom = () =>
      Math.abs(scrollEl.scrollHeight - scrollEl.scrollTop - scrollEl.clientHeight) <= 1 ||
      scrollEl.scrollHeight <= scrollEl.clientHeight;

    const pin = () => {
      if (!pinned) return;
      scrollEl.scrollTop = scrollEl.scrollHeight;
    };
    // 内容增长导致滚动高度增加后，图钉自身的滚动事件可能延迟到达并被判定为“脱离底部”；
    // 仅当滚动高度未变但位置向上移动时，才视作用户的真实向上滚动意图。
    const onScroll = () => {
      if (isAtBottom()) {
        pinned = true;
      } else if (scrollEl.scrollTop < lastScrollTop && scrollEl.scrollHeight === lastScrollHeight) {
        pinned = false;
      }
      lastScrollTop = scrollEl.scrollTop;
      lastScrollHeight = scrollEl.scrollHeight;
    };

    pin();
    scrollEl.addEventListener("scroll", onScroll);
    const observer = new ResizeObserver(pin);
    observer.observe(contentEl);
    return () => {
      scrollEl.removeEventListener("scroll", onScroll);
      observer.disconnect();
    };
  }, [isPreview]);

  return (
    <div
      ref={scrollRef}
      data-slot="reasoning-text"
      className={cn(
        "aui-reasoning-text relative z-0 max-h-64 overflow-y-auto ps-6 pt-2 pb-2 leading-relaxed text-pretty",
        "transform-gpu transition-[transform,opacity] ease-[cubic-bezier(0.32,0.72,0,1)]",
        "motion-reduce:animate-none",
        "group-data-open/collapsible-content:animate-in",
        "group-data-closed/collapsible-content:animate-out",
        "group-data-open/collapsible-content:fade-in-0",
        "group-data-closed/collapsible-content:fade-out-0",
        "group-data-open/collapsible-content:slide-in-from-top-4",
        "group-data-closed/collapsible-content:slide-out-to-top-4",
        "group-data-open/collapsible-content:blur-in-[2px]",
        "group-data-closed/collapsible-content:blur-out-[2px]",
        "group-data-open/collapsible-content:animation-duration-(--animation-duration)",
        "group-data-closed/collapsible-content:animation-duration-(--animation-duration)",
        className,
      )}
      {...props}
    >
      <div ref={contentRef} className="aui-reasoning-text-content space-y-4">
        {children}
      </div>
    </div>
  );
}

export { ReasoningRoot, ReasoningTrigger, ReasoningContent, ReasoningText };
