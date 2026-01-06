import { useState } from "react";
import { Card } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { AlertCircle, Send, RotateCcw, Info, CheckCircle2 } from "lucide-react";
import { cn } from "@/lib/utils";

interface TicketFormProps {
  onSubmit: (alert: any) => void;
  isLoading: boolean;
  error?: string;
}

const allowedCategories = [
  "database",
  "network",
  "application",
  "infrastructure",
  "security",
  "other",
];

// Removed emptyLabels - using real test incident data instead

const makeInitialAlert = () => {
  // Sample test incident from test_incidents.csv (INC6039763)
  // This is a real database job failure incident
  return {
    alert_id: "INC6039763",
    title: "SentryOne Monitoring/Alert",
    description: `The SQL Server Agent job 'BACKUP_Native_SYS_DB_Full' failed on server BRPRWSQL506.INT.MGC.COM.

Error: Unable to determine if the owner (INT\\Ssubramanian) has server access. Could not obtain information about Windows NT group/user 'INT\\Ssubramanian', error code 0x5. [SQLSTATE 42000] (Error 15404).

The job failed immediately (duration: 0 seconds) at 10/29/2025 7:00:00 PM. This is a database maintenance job from Ola Hallengren's maintenance solution.`,
    source: "servicenow",
    category: "Monitoring/Alert",
    labels: {
      service: "Database-SQL",
      component: "Database",
      cmdb_ci: "Database-SQL",
      environment: "production",
      severity: "high",
      alertname: "SQLServerAgentJobFailure",
    },
    affected_services: ["Database-SQL"], // Top-level field, not in labels
    ts: "2025-10-29T19:01:00",
  };
};

export const TicketForm = ({ onSubmit, isLoading, error }: TicketFormProps) => {
  const [alert, setAlert] = useState(makeInitialAlert());
  const [validationErrors, setValidationErrors] = useState<
    Record<string, string>
  >({});
  const [touchedFields, setTouchedFields] = useState<Set<string>>(new Set());

  const validateField = (field: string, value: string) => {
    const errors: Record<string, string> = {};

    switch (field) {
      case "alert_id":
        if (!value.trim()) {
          errors[field] = "Alert ID is required";
        } else if (value.length < 3) {
          errors[field] = "Alert ID must be at least 3 characters";
        }
        break;
      case "source":
        if (!value.trim()) {
          errors[field] = "Source is required";
        }
        break;
      case "title":
        if (!value.trim()) {
          errors[field] = "Title is required";
        } else if (value.length < 10) {
          errors[field] =
            "Title should be at least 10 characters for better analysis";
        }
        break;
      case "description":
        if (!value.trim()) {
          errors[field] = "Description is required";
        } else if (value.length < 20) {
          errors[field] =
            "Description should be at least 20 characters for accurate triage";
        }
        break;
      case "service":
        if (!value.trim()) {
          errors[field] = "Service is required";
        }
        break;
      case "component":
        if (!value.trim()) {
          errors[field] = "Component is required";
        }
        break;
    }

    return errors;
  };

  const handleAlertChange = (field: string, value: string) => {
    setAlert((prev) => ({ ...prev, [field]: value }));
    setTouchedFields((prev) => new Set([...prev, field]));

    const errors = validateField(field, value);
    setValidationErrors((prev) => {
      const updated = { ...prev };
      if (Object.keys(errors).length > 0) {
        Object.assign(updated, errors);
      } else {
        delete updated[field];
      }
      return updated;
    });
  };

  const handleLabelChange = (field: string, value: string) => {
    setAlert((prev) => {
      const nextLabels = { ...prev.labels, [field]: value };
      if (field === "category") {
        return { ...prev, category: value, labels: nextLabels };
      }
      return { ...prev, labels: nextLabels };
    });

    setTouchedFields((prev) => new Set([...prev, field]));
    const errors = validateField(field, value);
    setValidationErrors((prev) => {
      const updated = { ...prev };
      if (Object.keys(errors).length > 0) {
        Object.assign(updated, errors);
      } else {
        delete updated[field];
      }
      return updated;
    });
  };

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();

    // Validate all fields
    const allErrors: Record<string, string> = {};
    Object.entries({
      alert_id: alert.alert_id,
      source: alert.source,
      title: alert.title,
      description: alert.description,
      service: alert.labels.service,
      component: alert.labels.component,
    }).forEach(([field, value]) => {
      const errors = validateField(field, value);
      Object.assign(allErrors, errors);
    });

    if (Object.keys(allErrors).length > 0) {
      setValidationErrors(allErrors);
      // Mark all fields as touched
      setTouchedFields(new Set(Object.keys(allErrors)));
      return;
    }

    onSubmit(alert);
  };

  const handleReset = () => {
    setAlert(makeInitialAlert());
    setValidationErrors({});
    setTouchedFields(new Set());
  };

  const getFieldStatus = (field: string) => {
    if (!touchedFields.has(field)) return null;
    return validationErrors[field] ? "error" : "success";
  };

  return (
    <Card className="p-6 glass-card glow-border relative">
      {/* Loading Overlay */}
      {isLoading && (
        <div className="absolute inset-0 bg-background/80 backdrop-blur-sm z-10 flex items-center justify-center rounded-lg">
          <div className="text-center space-y-4">
            <div className="w-16 h-16 border-4 border-primary border-t-transparent rounded-full animate-spin mx-auto" />
            <div className="space-y-2">
              <p className="text-lg font-semibold text-foreground">
                Analyzing Alert...
              </p>
              <p className="text-sm text-muted-foreground">
                AI is processing your ticket. Please wait.
              </p>
            </div>
          </div>
        </div>
      )}

      <div className="flex items-center gap-3 mb-6">
        <div className="p-2 rounded-lg bg-primary/10">
          <AlertCircle className="w-5 h-5 text-primary" />
        </div>
        <div className="flex-1">
          <h2 className="text-xl font-semibold text-foreground">New Ticket</h2>
          <p className="text-sm text-muted-foreground">
            Submit an alert for AI triage analysis
          </p>
        </div>
        {Object.keys(validationErrors).length === 0 &&
          touchedFields.size > 0 &&
          !isLoading && (
            <div className="flex items-center gap-2 text-success text-sm">
              <CheckCircle2 className="w-4 h-4" />
              <span>All fields valid</span>
            </div>
          )}
      </div>

      <form onSubmit={handleSubmit} className="space-y-6">
        {/* Alert ID and Source */}
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          <FormField
            label="Alert ID"
            id="alert_id"
            value={alert.alert_id}
            onChange={(value) => handleAlertChange("alert_id", value)}
            required
            disabled={isLoading}
            status={getFieldStatus("alert_id")}
            error={
              touchedFields.has("alert_id")
                ? validationErrors.alert_id
                : undefined
            }
            tooltip="Unique identifier for this alert (e.g., sample-match-1)"
          />
          <FormField
            label="Source"
            id="source"
            value={alert.source}
            onChange={(value) => handleAlertChange("source", value)}
            required
            disabled={isLoading}
            status={getFieldStatus("source")}
            error={
              touchedFields.has("source") ? validationErrors.source : undefined
            }
            tooltip="Alert source system (e.g., prometheus, datadog, splunk)"
          />
        </div>

        {/* Service and Component */}
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          <FormField
            label="Service"
            id="service"
            value={alert.labels.service}
            onChange={(value) => handleLabelChange("service", value)}
            placeholder="database"
            required
            disabled={isLoading}
            status={getFieldStatus("service")}
            error={
              touchedFields.has("service")
                ? validationErrors.service
                : undefined
            }
            tooltip="Service category (e.g., Database, Network, Application)"
          />
          <FormField
            label="Component"
            id="component"
            value={alert.labels.component}
            onChange={(value) => handleLabelChange("component", value)}
            placeholder="sql-server"
            required
            disabled={isLoading}
            status={getFieldStatus("component")}
            error={
              touchedFields.has("component")
                ? validationErrors.component
                : undefined
            }
            tooltip="Specific component within the service"
          />
        </div>

        {/* CMDB CI and Category */}
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          <FormField
            label="CMDB CI"
            id="cmdb_ci"
            value={alert.labels.cmdb_ci}
            onChange={(value) => handleLabelChange("cmdb_ci", value)}
            placeholder="Database-SQL"
            disabled={isLoading}
            tooltip="Configuration Item from your CMDB"
          />
          <div className="space-y-2">
            <div className="flex items-center gap-2">
              <Label htmlFor="category">Category *</Label>
              <TooltipIcon text="Alert category for routing and analysis" />
            </div>
            <select
              id="category"
              value={alert.category || ""}
              onChange={(e) => handleAlertChange("category", e.target.value)}
              required
              disabled={isLoading}
              className="flex h-10 w-full rounded-md border border-border/50 bg-secondary/50 px-3 py-2 text-sm text-foreground ring-offset-background file:border-0 file:bg-transparent file:text-sm file:font-medium placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary focus-visible:ring-offset-2 disabled:cursor-not-allowed disabled:opacity-50 transition-all"
            >
              {allowedCategories.map((cat) => (
                <option key={cat} value={cat}>
                  {cat.charAt(0).toUpperCase() + cat.slice(1)}
                </option>
              ))}
            </select>
          </div>
        </div>

        {/* Title */}
        <FormField
          label="Title"
          id="title"
          value={alert.title}
          onChange={(value) => handleAlertChange("title", value)}
          required
          disabled={isLoading}
          status={getFieldStatus("title")}
          error={
            touchedFields.has("title") ? validationErrors.title : undefined
          }
          tooltip="Brief, descriptive title for the alert"
        />

        {/* Description */}
        <div className="space-y-2">
          <div className="flex items-center gap-2">
            <Label htmlFor="description">Description *</Label>
            <TooltipIcon text="Detailed description helps AI provide more accurate triage" />
          </div>
          <Textarea
            id="description"
            value={alert.description}
            onChange={(e) => handleAlertChange("description", e.target.value)}
            required
            disabled={isLoading}
            rows={5}
            className={cn(
              "bg-secondary/50 border-border/50 resize-none transition-all",
              touchedFields.has("description") &&
                validationErrors.description &&
                "border-destructive focus-visible:ring-destructive",
              touchedFields.has("description") &&
                !validationErrors.description &&
                "border-success focus-visible:ring-success",
            )}
            placeholder="Provide detailed information about the alert, including metrics, thresholds, and impact..."
          />
          {touchedFields.has("description") && validationErrors.description && (
            <p className="text-xs text-destructive flex items-center gap-1">
              <AlertCircle className="w-3 h-3" />
              {validationErrors.description}
            </p>
          )}
          <p className="text-xs text-muted-foreground flex items-center gap-1">
            <Info className="w-3 h-3" />
            {alert.description.length} characters - Recommended: 50+ for best
            results
          </p>
        </div>

        {/* Timestamp */}
        <FormField
          label="Timestamp"
          id="timestamp"
          value={alert.ts}
          onChange={(value) => handleAlertChange("ts", value)}
          placeholder={new Date().toISOString()}
          disabled={isLoading}
          tooltip="ISO 8601 timestamp (auto-generated if not provided)"
        />

        {/* Submit Buttons */}
        <div className="flex gap-3 pt-4">
          <Button
            type="submit"
            disabled={isLoading || Object.keys(validationErrors).length > 0}
            className="flex-1 bg-primary hover:bg-primary/90 text-primary-foreground disabled:opacity-50 transition-all"
          >
            {isLoading ? (
              <>
                <div className="w-4 h-4 border-2 border-current border-t-transparent rounded-full animate-spin mr-2" />
                Analyzing...
              </>
            ) : (
              <>
                <Send className="w-4 h-4 mr-2" />
                Submit & Triage
              </>
            )}
          </Button>
          <Button
            type="button"
            variant="outline"
            onClick={handleReset}
            disabled={isLoading}
            className="bg-secondary hover:bg-secondary/80 transition-all"
          >
            <RotateCcw className="w-4 h-4 mr-2" />
            Reset
          </Button>
        </div>

        {/* Error Display */}
        {error && (
          <div className="p-4 rounded-lg bg-destructive/10 border border-destructive/30 text-destructive animate-slide-up">
            <div className="flex items-start gap-2">
              <AlertCircle className="w-5 h-5 flex-shrink-0 mt-0.5" />
              <div>
                <div className="font-semibold">Error</div>
                <div className="text-sm mt-1">{error}</div>
              </div>
            </div>
          </div>
        )}
      </form>
    </Card>
  );
};

// Reusable Form Field Component
interface FormFieldProps {
  label: string;
  id: string;
  value: string;
  onChange: (value: string) => void;
  placeholder?: string;
  required?: boolean;
  disabled?: boolean;
  status?: "error" | "success" | null;
  error?: string;
  tooltip?: string;
}

const FormField = ({
  label,
  id,
  value,
  onChange,
  placeholder,
  required,
  disabled,
  status,
  error,
  tooltip,
}: FormFieldProps) => {
  return (
    <div className="space-y-2">
      <div className="flex items-center gap-2">
        <Label htmlFor={id}>
          {label} {required && "*"}
        </Label>
        {tooltip && <TooltipIcon text={tooltip} />}
      </div>
      <div className="relative">
        <Input
          id={id}
          value={value}
          onChange={(e) => onChange(e.target.value)}
          placeholder={placeholder}
          required={required}
          disabled={disabled}
          className={cn(
            "bg-secondary/50 border-border/50 transition-all",
            status === "error" &&
              "border-destructive focus-visible:ring-destructive",
            status === "success" && "border-success focus-visible:ring-success",
            disabled && "opacity-60 cursor-not-allowed",
          )}
        />
        {status === "success" && !disabled && (
          <CheckCircle2 className="w-4 h-4 text-success absolute right-3 top-1/2 -translate-y-1/2" />
        )}
      </div>
      {error && (
        <p className="text-xs text-destructive flex items-center gap-1 animate-fade-in">
          <AlertCircle className="w-3 h-3" />
          {error}
        </p>
      )}
    </div>
  );
};

// Tooltip Icon Component
const TooltipIcon = ({ text }: { text: string }) => {
  return (
    <div className="group relative inline-block">
      <Info className="w-3.5 h-3.5 text-muted-foreground hover:text-primary cursor-help transition-colors" />
      <div className="hidden group-hover:block absolute z-10 w-64 p-2 text-xs text-foreground bg-background border border-border rounded-lg shadow-lg left-0 top-5">
        {text}
      </div>
    </div>
  );
};
