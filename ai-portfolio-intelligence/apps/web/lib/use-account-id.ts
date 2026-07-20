"use client";

import { useSearchParams } from "next/navigation";

export function useAccountId(): string | undefined {
  const searchParams = useSearchParams();
  return searchParams.get("account_id") || undefined;
}
