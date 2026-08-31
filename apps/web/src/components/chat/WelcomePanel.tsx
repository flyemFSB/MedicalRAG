// 欢迎屏（空会话时的引导 + 样例问题）。
import { useQuery } from "@tanstack/react-query";
import { ArrowRight } from "lucide-react";
import { sampleQuestionsQueryOptions } from "../../lib/queries";

export function WelcomePanel({ onAsk }: { onAsk: (question: string) => void }) {
  const { data: questions = [] } = useQuery(sampleQuestionsQueryOptions());
  const suggestions = questions.filter((q) => q.enabled).slice(0, 4);

  return (
    <div className="mx-auto flex min-h-[60vh] w-full max-w-[760px] flex-col justify-center px-4 py-10 sm:px-8">
      <p className="mb-3 font-mono text-caption text-muted-foreground">
        Evidence-first · 循证问答
      </p>
      <h1 className="max-w-[16ch] font-sans text-display font-semibold text-balance text-ink">
        每个答案，都有据可查。
      </h1>
      <p className="mt-3 max-w-[46ch] text-body text-muted-foreground">
        面向医疗来源的循证问答：检索你的知识库、标注证据来源，并在涉及治疗、用药或急症时明确安全边界。
      </p>
      {suggestions.length > 0 ? (
        <div className="mt-8">
          <p className="mb-2 text-caption font-medium text-muted-foreground">试着问</p>
          <div className="space-y-1">
            {suggestions.map((q) => (
              <button
                key={q.id}
                type="button"
                onClick={() => onAsk(q.text)}
                className="group flex w-full items-center justify-between gap-3 rounded-md border border-border bg-surface px-4 py-3 text-left text-body-sm text-ink outline-none transition-colors hover:border-accent-ink hover:bg-accent-soft focus-visible:ring-2 focus-visible:ring-ring"
              >
                <span>{q.text}</span>
                <ArrowRight
                  className="size-4 shrink-0 text-muted-foreground transition-transform group-hover:translate-x-0.5"
                  aria-hidden
                />
              </button>
            ))}
          </div>
        </div>
      ) : null}
      <p className="mt-8 flex items-center gap-2 text-caption text-muted-foreground">
        <span className="size-1.5 shrink-0 rounded-full bg-medical" aria-hidden />
        涉及治疗 / 用药 / 急症时，会先展示安全边界。
      </p>
    </div>
  );
}
