"use client";

import { memo, useCallback, useRef } from "react";
import { useScrollLock, type ReasoningMessagePartComponent } from "@assistant-ui/react";
import { MarkdownText } from "@/components/assistant-ui/elements/markdown-text";
import {
  ANIMATION_DURATION,
  ReasoningRoot as ReasoningRootBase,
  ReasoningTrigger,
  ReasoningContent,
  ReasoningText,
  type ReasoningRootProps,
} from "./reasoning";

export type { ReasoningRootProps } from "./reasoning";

/** 在折叠展开动画期间锁定线程视口滚动的 ReasoningRoot 容器。 */
function ReasoningRoot({ ref, onAnimationStart, ...props }: ReasoningRootProps) {
  const collapsibleRef = useRef<HTMLDivElement | null>(null);
  const lockScroll = useScrollLock(collapsibleRef, ANIMATION_DURATION);

  const handleAnimationStart = useCallback(() => {
    lockScroll();
    onAnimationStart?.();
  }, [lockScroll, onAnimationStart]);

  const composedRef = useCallback(
    (node: HTMLDivElement | null) => {
      collapsibleRef.current = node;
      if (typeof ref === "function") {
        ref(node);
      } else if (ref) {
        ref.current = node;
      }
    },
    [ref],
  );

  return <ReasoningRootBase ref={composedRef} onAnimationStart={handleAnimationStart} {...props} />;
}

const ReasoningImpl: ReasoningMessagePartComponent = () => <MarkdownText />;

const Reasoning = memo(ReasoningImpl) as unknown as ReasoningMessagePartComponent;
Reasoning.displayName = "Reasoning";

export { Reasoning, ReasoningRoot, ReasoningTrigger, ReasoningContent, ReasoningText };
