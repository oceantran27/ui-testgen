const CDN_BASE_URL = (import.meta.env.VITE_CDN_BASE_URL ?? "").replace(
  /\/$/,
  "",
);

const trimLeadingSlash = (value: string): string => value.replace(/^\/+/, "");

export const toCdnUrl = (rawUrl: string): string => {
  if (!rawUrl) {
    return rawUrl;
  }

  if (rawUrl.startsWith("blob:") || rawUrl.startsWith("data:")) {
    return rawUrl;
  }

  // Keep presigned URLs untouched because signature query params are host/path sensitive.
  if (
    /[?&]X-Amz-(Algorithm|Signature|Credential|Date|Expires)=/i.test(rawUrl)
  ) {
    return rawUrl;
  }

  if (!CDN_BASE_URL) {
    return rawUrl;
  }

  if (/^https?:\/\//i.test(rawUrl)) {
    try {
      const parsed = new URL(rawUrl);
      return `${CDN_BASE_URL}/${trimLeadingSlash(parsed.pathname)}${parsed.search}${parsed.hash}`;
    } catch {
      return rawUrl;
    }
  }

  return `${CDN_BASE_URL}/${trimLeadingSlash(rawUrl)}`;
};
