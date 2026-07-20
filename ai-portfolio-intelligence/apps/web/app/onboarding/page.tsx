"use client";

/**
 * Desktop onboarding: currency, tax jurisdiction, IBKR local connection.
 * No application account is created.
 */
export default function OnboardingPage() {
  return (
    <main className="mx-auto max-w-2xl px-6 py-12">
      <h1 className="text-3xl font-semibold tracking-tight">Welcome</h1>
      <p className="mt-3 text-zinc-600">
        Portfolio Analyzer runs entirely on this computer. There is no application account,
        subscription login, or cloud portfolio storage.
      </p>

      <ol className="mt-10 space-y-6 text-sm leading-6 text-zinc-800">
        <li>
          <strong className="block text-base">1. Choose base currency and tax jurisdiction</strong>
          Configure reporting preferences in Settings after first launch.
        </li>
        <li>
          <strong className="block text-base">2. Start IBKR Client Portal Gateway</strong>
          Authenticate directly with Interactive Brokers. This app never asks for your IBKR
          username, password, or 2FA code.
        </li>
        <li>
          <strong className="block text-base">3. Return here and check connection</strong>
          Use Settings → Broker to verify the local Gateway link and select accounts to import.
        </li>
        <li>
          <strong className="block text-base">4. Optional Flex token</strong>
          If you enter a Flex token, it is stored only in your OS keychain on this device.
        </li>
      </ol>

      <p className="mt-10 text-xs text-zinc-500">
        Outputs are informational decision-support for the account owner. The system does not
        place orders.
      </p>
    </main>
  );
}
