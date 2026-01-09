import { useState } from "react";

interface ExpandableTextProps {
  text: string;
  charLimit?: number;
  lineLimit?: number;
  className?: string;
  buttonClassName?: string;
  showButtonText?: { more: string; less: string };
}

/**
 * ExpandableText component that shows truncated text with a "more"/"less" button
 * Supports both character-based and line-based truncation
 */
export const ExpandableText = ({
  text,
  charLimit,
  lineLimit,
  className = "",
  buttonClassName = "",
  showButtonText = { more: "more", less: "less" },
}: ExpandableTextProps) => {
  const [isExpanded, setIsExpanded] = useState(false);

  // Handle null/undefined text
  if (!text || typeof text !== "string") {
    return <span className={className}>N/A</span>;
  }

  // Character-based truncation
  if (charLimit) {
    const isTruncated = text.length > charLimit;
    const truncated = isTruncated ? text.substring(0, charLimit) + "..." : text;

    if (!isTruncated) {
      return <span className={className}>{text}</span>;
    }

    return (
      <div className={className}>
        <span>{isExpanded ? text : truncated}</span>
        <button
          onClick={() => setIsExpanded(!isExpanded)}
          className={`ml-2 text-primary hover:underline text-xs font-medium ${buttonClassName}`}
        >
          {isExpanded ? showButtonText.less : showButtonText.more}
        </button>
      </div>
    );
  }

  // Line-based truncation (using CSS line-clamp)
  if (lineLimit) {
    // Estimate if text would overflow (rough heuristic: ~80 chars per line)
    const estimatedLines = Math.ceil(text.length / 80);
    const wouldOverflow = estimatedLines > lineLimit;

    // Use inline styles for line-clamp to ensure it works across all browsers
    const lineClampStyle = isExpanded
      ? {}
      : {
          display: "-webkit-box",
          WebkitLineClamp: lineLimit,
          WebkitBoxOrient: "vertical" as const,
          overflow: "hidden",
        };

    // Always show button if text is long enough, let CSS handle the truncation
    if (!wouldOverflow) {
      return <div className={className}>{text}</div>;
    }

    return (
      <div className={className}>
        <div style={lineClampStyle}>{text}</div>
        <button
          onClick={() => setIsExpanded(!isExpanded)}
          className={`mt-1 text-primary hover:underline text-xs font-medium ${buttonClassName}`}
        >
          {isExpanded ? showButtonText.less : showButtonText.more}
        </button>
      </div>
    );
  }

  // No truncation specified, return as-is
  return <span className={className}>{text}</span>;
};
