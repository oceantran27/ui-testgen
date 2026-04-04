interface AnalysisResultDisplayProps {
  result: string;
  showTitle?: boolean;
  className?: string;
}

export function AnalysisResultDisplay({
  result,
  showTitle = true,
  className = "",
}: AnalysisResultDisplayProps) {
  if (!result) {
    return null;
  }

  let displayContent = result;
  try {
    const jsonObj = JSON.parse(result);
    displayContent = JSON.stringify(jsonObj, null, 2);
  } catch {
    // Keep plain text output when the response is not valid JSON.
  }

  return (
    <div className={`card ${className}`}>
      {showTitle && (
        <h2 className="mb-4 text-2xl font-bold text-gray-700">
          Analysis Result
        </h2>
      )}
      <pre className="custom-scrollbar overflow-x-auto rounded-lg border border-gray-200/80 bg-gray-50/80 p-3 text-sm">
        {displayContent}
      </pre>
    </div>
  );
}
