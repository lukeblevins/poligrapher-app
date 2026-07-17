import * as TooltipPrimitive from "@radix-ui/react-tooltip";
import type { ComponentPropsWithoutRef, ReactElement, ReactNode } from "react";

type TooltipContentProps = ComponentPropsWithoutRef<typeof TooltipPrimitive.Content>;

export function TooltipProvider({ children }: { children: ReactNode }) {
  return (
    <TooltipPrimitive.Provider delayDuration={350} skipDelayDuration={200} disableHoverableContent>
      {children}
    </TooltipPrimitive.Provider>
  );
}

export function Tooltip({
  content,
  children,
  side = "top",
  align = "center",
  disabled = false,
}: {
  content: ReactNode;
  children: ReactElement;
  side?: TooltipContentProps["side"];
  align?: TooltipContentProps["align"];
  disabled?: boolean;
}) {
  if (disabled) return children;

  return (
    <TooltipPrimitive.Root>
      <TooltipPrimitive.Trigger asChild>{children}</TooltipPrimitive.Trigger>
      <TooltipPrimitive.Portal>
        <TooltipPrimitive.Content
          side={side}
          align={align}
          sideOffset={7}
          avoidCollisions
          collisionPadding={12}
          sticky="always"
          className="z-50 max-h-[min(20rem,calc(100dvh-2rem))] w-max max-w-[min(20rem,calc(100vw-2rem))] select-none overflow-y-auto rounded-lg border border-slate-500 bg-slate-950 px-3 py-2.5 text-left text-xs font-normal leading-5 tracking-normal text-slate-100 shadow-xl"
        >
          {content}
          <TooltipPrimitive.Arrow className="fill-slate-950" width={10} height={5} />
        </TooltipPrimitive.Content>
      </TooltipPrimitive.Portal>
    </TooltipPrimitive.Root>
  );
}
