export interface WidgetWrite {
  enabled: boolean; title: string; greeting: string; color: string; position: 'left' | 'right';
  allowed_origins: string[]; requests_per_minute: number; requests_per_day: number;
}
export interface WebsiteWidget extends WidgetWrite {
  id: string; assistant_id: string; revision: number; public_origin: string;
  public_access_enabled: boolean; requests_today: number;
}
