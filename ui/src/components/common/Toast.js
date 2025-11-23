import React from "react";
import "./Toast.css";

const Toast = ({ toast, onRemove }) => {
  const handleRemove = () => {
    onRemove(toast.id);
  };

  React.useEffect(() => {
    if (toast.duration > 0) {
      const timer = setTimeout(() => {
        onRemove(toast.id);
      }, toast.duration);
      return () => clearTimeout(timer);
    }
  }, [toast, onRemove]);

  const getIcon = () => {
    switch (toast.type) {
      case "success":
        return "✓";
      case "error":
        return "✕";
      case "warning":
        return "⚠";
      default:
        return "ℹ";
    }
  };

  return (
    <div className={`toast toast--${toast.type}`} onClick={handleRemove}>
      <span className="toast__icon">{getIcon()}</span>
      <span className="toast__message">{toast.message}</span>
      <button className="toast__close" onClick={handleRemove} aria-label="Close">
        ×
      </button>
    </div>
  );
};

export default Toast;

