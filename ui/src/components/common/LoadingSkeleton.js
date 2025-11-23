import React from "react";
import "./LoadingSkeleton.css";

const LoadingSkeleton = ({ 
  variant = "text", 
  width, 
  height, 
  count = 1,
  className = "" 
}) => {
  const skeletons = Array.from({ length: count }, (_, i) => (
    <div
      key={i}
      className={`skeleton skeleton--${variant} ${className}`}
      style={{
        width: width || (variant === "text" ? "100%" : undefined),
        height: height || (variant === "text" ? "1rem" : undefined),
      }}
    />
  ));

  return <>{skeletons}</>;
};

export const CardSkeleton = () => (
  <div className="skeleton-card">
    <LoadingSkeleton variant="rect" height="20px" width="60px" />
    <LoadingSkeleton variant="text" count={2} />
    <LoadingSkeleton variant="text" width="80%" />
  </div>
);

export const ListSkeleton = ({ count = 5 }) => (
  <div className="skeleton-list">
    {Array.from({ length: count }, (_, i) => (
      <CardSkeleton key={i} />
    ))}
  </div>
);

export default LoadingSkeleton;

