import { Toaster } from "react-hot-toast";
import { Navigate, Route, Routes } from "react-router-dom";
import { AdminCRUD } from "./components/AdminCRUD.tsx";
import { Error404Page } from "./components/Error404Page.tsx";
import { RunListPage } from "./components/runs/RunListPage";
import { RunWorkspacePage } from "./components/run-workspace/RunWorkspacePage";

function App() {
  return (
    <>
      <Toaster
        position="top-center"
        reverseOrder={false}
        toastOptions={{
          className:
            "rounded-xl border border-zinc-700/90 bg-zinc-900/95 text-zinc-100 shadow-xl",
          duration: 4000,
        }}
      />
      <Routes>
        <Route path="/" element={<RunListPage />} />
        <Route path="/runs/:runId" element={<RunWorkspacePage />} />
        <Route path="/behavior-flows" element={<Navigate to="/" replace />} />
        <Route path="/admin" element={<AdminCRUD />} />
        <Route path="/404" element={<Error404Page />} />
        <Route path="*" element={<Navigate to="/404" replace />} />
      </Routes>
    </>
  );
}

export default App;
