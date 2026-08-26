import Nav from "@/components/Nav";

export default function OperatorLayout({ children }: { children: React.ReactNode }) {
  return (
    <div className="layout">
      <Nav />
      <main className="main">{children}</main>
    </div>
  );
}
