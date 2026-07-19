import LoginForm from "./LoginForm";

export default function Page() {
  return (
    <div className="mx-auto flex min-h-[70vh] max-w-md flex-col justify-center">
      <div className="rounded-lg border border-line bg-white p-6 shadow-sm">
        <h1 className="text-2xl font-semibold">Sign in</h1>
        <p className="mt-2 text-sm text-zinc-600">
          Authenticate to access portfolio intelligence. Public registration is disabled by default.
        </p>
        <LoginForm />
      </div>
    </div>
  );
}
