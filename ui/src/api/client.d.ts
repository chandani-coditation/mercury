declare module "@/api/client" {
  export function postTriage(payload: any): Promise<any>;
  export function getIncident(incidentId: string): Promise<any>;
  export function listIncidents(
    limit?: number,
    offset?: number,
    search?: string | null,
  ): Promise<{
    incidents: any[];
    count: number;
    total: number;
    limit: number;
    offset: number;
  }>;
  export function putFeedback(
    incidentId: string,
    payload: any,
  ): Promise<any>;
  export function postResolution(
    incidentId: string,
    payload?: any | null,
  ): Promise<any>;
  export function putResolutionComplete(
    incidentId: string,
    payload?: any,
  ): Promise<any>;
}


