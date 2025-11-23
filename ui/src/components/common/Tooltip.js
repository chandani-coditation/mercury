import React, { useState } from "react";
import "./Tooltip.css";

const Tooltip = ({ children, content, position = "top", disabled = false }) => {
  const [isVisible, setIsVisible] = useState(false);

  if (disabled || !content) {
    return <>{children}</>;
  }

  return (
    <div
      className="tooltip-wrapper"
      onMouseEnter={() => setIsVisible(true)}
      onMouseLeave={() => setIsVisible(false)}
      onFocus={() => setIsVisible(true)}
      onBlur={() => setIsVisible(false)}
    >
      {children}
      {isVisible && (
        <div className={`tooltip tooltip--${position}`} role="tooltip">
          {content}
        </div>
      )}
    </div>
  );
};

export default Tooltip;

