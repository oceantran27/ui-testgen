import { useMemo, useState } from "react";
import axios from "axios";
import { apiClient } from "../api/client";
import { toCdnUrl } from "../utils/cdn";

interface PresignedResponse {
  upload_url?: string;
  uploadUrl?: string;
  file_url?: string;
  fileUrl?: string;
  file_key?: string;
  fileKey?: string;
  session_id?: string;
  sessionId?: string;
  notify_url?: string;
  notifyUrl?: string;
  headers?: Record<string, string>;
  method?: string;
}

interface UploadResult {
  fileUrl: string;
  cdnUrl: string;
  fileKey?: string;
  sessionId?: string;
}

const PRESIGNED_URL_ENDPOINT = "/api/v1/presigned-url";
const SESSION_SAVE_ENDPOINT = "/api/v1/upload-session";

// Generate UUID v4
function generateSessionId(): string {
  return crypto.randomUUID?.() || `${Date.now()}-${Math.random()}`;
}

export const useImageUpload = () => {
  const [isUploading, setIsUploading] = useState(false);
  const [uploadError, setUploadError] = useState<string | null>(null);
  const [progress, setProgress] = useState(0);

  const resetUploadState = () => {
    setUploadError(null);
    setProgress(0);
  };

  const uploadImage = async (file: File): Promise<UploadResult> => {
    setIsUploading(true);
    setUploadError(null);
    setProgress(0);

    try {
      // Use backend endpoint to upload to B2 (server-to-server, no CORS issues)
      const formData = new FormData();
      formData.append("file", file);

      const response = await axios.post<{ file_url: string; file_key: string }>(
        "/api/v1/upload-to-b2",
        formData,
        {
          // Don't set Content-Type header manually when using FormData
          // axios will automatically set "multipart/form-data; boundary=..." with correct boundary
          headers: {},
          onUploadProgress: (evt) => {
            if (evt.total) {
              setProgress(Math.round((evt.loaded / evt.total) * 100));
            }
          },
        },
      );

      const fileUrl = response.data.file_url;
      const fileKey = response.data.file_key;
      const sessionId = generateSessionId();
      const notifyEndpoint = "/api/v1/upload-session";

      // Notify session
      await apiClient.post(notifyEndpoint, {
        session_id: sessionId,
        file_key: fileKey,
        file_url: fileUrl,
        original_name: file.name,
        content_type: file.type,
        size: file.size,
      });

      return {
        fileUrl,
        cdnUrl: toCdnUrl(fileUrl),
        fileKey,
        sessionId,
      };
    } catch (error) {
      const message = axios.isAxiosError(error)
        ? (error.response?.data?.detail ?? error.message)
        : "Failed to upload image.";
      const normalized =
        typeof message === "string" ? message : "Failed to upload image.";
      setUploadError(normalized);
      throw new Error(normalized);
    } finally {
      setIsUploading(false);
    }
  };

  return useMemo(
    () => ({
      uploadImage,
      isUploading,
      uploadError,
      progress,
      resetUploadState,
    }),
    [isUploading, uploadError, progress],
  );
};
