import {
  FiChevronDown,
  FiChevronRight,
  FiImage,
  FiServer,
  FiTrash2,
} from "react-icons/fi";
import { AnalysisResultDisplay } from "./AnalysisResultDisplay";
import type { AnalysisRecord } from "./types";

interface AnalysisHistoryPanelProps {
  records: AnalysisRecord[];
  expandedRecordId: number | null;
  onToggleExpand: (recordId: number) => void;
  onHistoryImageClick: (src: string) => void;
  onDeleteRecord: (recordId: number) => void;
  resolveImageSrc: (path: string) => string;
}

export function AnalysisHistoryPanel({
  records,
  expandedRecordId,
  onToggleExpand,
  onHistoryImageClick,
  onDeleteRecord,
  resolveImageSrc,
}: AnalysisHistoryPanelProps) {
  return (
    <div className="card row-span-2 lg:col-span-3">
      <h2 className="mb-4 flex items-center text-2xl font-bold text-gray-700">
        <FiServer className="mr-3 text-blue-500" />
        Analysis History
      </h2>
      <div className="custom-scrollbar max-h-[75vh] space-y-4 overflow-y-auto pr-2">
        {records.length === 0 && (
          <div className="py-10 text-center text-gray-500">
            <FiImage className="mx-auto mb-2 text-4xl" />
            <p>No analysis records found.</p>
            <p className="text-sm">Upload a screenshot to get started.</p>
          </div>
        )}
        {records.map((record) => (
          <div
            key={record.id}
            className="group flex items-start space-x-4 rounded-xl border border-transparent bg-gray-50/80 p-4 transition-all hover:border-gray-200"
          >
            <div
              className="h-16 w-24 shrink-0 cursor-pointer rounded-md bg-gray-200"
              onClick={() =>
                onHistoryImageClick(resolveImageSrc(record.image_path))
              }
            >
              <img
                src={resolveImageSrc(record.image_path)}
                alt={`Record ${record.id}`}
                className="h-full w-full rounded-md object-cover"
              />
            </div>
            <div className="flex-1">
              <div className="flex items-center justify-between">
                <p className="font-semibold text-gray-700">
                  Record ID: {record.id}
                </p>
                <button
                  onClick={() => onToggleExpand(record.id)}
                  className="flex items-center text-sm font-medium text-blue-600 hover:text-blue-800"
                >
                  {expandedRecordId === record.id ? "Collapse" : "Expand"}
                  {expandedRecordId === record.id ? (
                    <FiChevronDown className="ml-1" />
                  ) : (
                    <FiChevronRight className="ml-1" />
                  )}
                </button>
              </div>
              <p className="text-sm text-gray-500">
                {new Date(record.created_at).toLocaleString()}
              </p>
              {expandedRecordId === record.id && (
                <AnalysisResultDisplay
                  result={record.scenario_json}
                  showTitle={false}
                  className="mt-2"
                />
              )}
            </div>
            <button
              onClick={() => onDeleteRecord(record.id)}
              className="rounded-full p-2 text-gray-400 opacity-0 transition-all hover:bg-red-100/50 hover:text-red-500 group-hover:opacity-100"
              aria-label="Delete record"
            >
              <FiTrash2 size={18} />
            </button>
          </div>
        ))}
      </div>
    </div>
  );
}
