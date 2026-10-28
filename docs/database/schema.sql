-- WARNING: This schema is for context only and is not meant to be run.
-- Table order and constraints may not be valid for execution.

CREATE TABLE public.account_selected_charts (
  id integer NOT NULL DEFAULT nextval('account_selected_charts_id_seq'::regclass),
  account_id integer NOT NULL,
  chart_id integer NOT NULL,
  created_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP,
  updated_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP,
  is_active boolean NOT NULL DEFAULT true,
  CONSTRAINT account_selected_charts_pkey PRIMARY KEY (id),
  CONSTRAINT account_selected_charts_account_fkey FOREIGN KEY (account_id) REFERENCES public.accounts(id),
  CONSTRAINT account_selected_charts_chart_fkey FOREIGN KEY (chart_id) REFERENCES public.platform_available_charts(id)
);
CREATE TABLE public.account_smtp_credentials (
  id integer NOT NULL DEFAULT nextval('account_smtp_credentials_id_seq'::regclass),
  account_id integer NOT NULL UNIQUE,
  smtp_email character varying NOT NULL,
  is_active boolean DEFAULT true,
  created_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP,
  updated_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP,
  azure_tenant_id character varying NOT NULL,
  azure_client_id character varying NOT NULL,
  azure_client_secret character varying NOT NULL,
  CONSTRAINT account_smtp_credentials_pkey PRIMARY KEY (id),
  CONSTRAINT account_smtp_credentials_account_fkey FOREIGN KEY (account_id) REFERENCES public.accounts(id)
);
CREATE TABLE public.accounts (
  id integer NOT NULL DEFAULT nextval('accounts_id_seq'::regclass),
  account_name character varying NOT NULL,
  subdomain character varying UNIQUE,
  status character varying DEFAULT 'Active'::character varying,
  created_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP,
  updated_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP,
  CONSTRAINT accounts_pkey PRIMARY KEY (id)
);
CREATE TABLE public.api_call_logs (
  id integer NOT NULL DEFAULT nextval('api_call_logs_id_seq'::regclass),
  account_id integer,
  organization_id integer,
  integration_name character varying,
  endpoint character varying NOT NULL,
  method character varying NOT NULL,
  status_code integer,
  response_time_ms integer,
  error_message text,
  called_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP,
  CONSTRAINT api_call_logs_pkey PRIMARY KEY (id),
  CONSTRAINT api_call_logs_account_id_fkey FOREIGN KEY (account_id) REFERENCES public.accounts(id),
  CONSTRAINT api_call_logs_organization_id_fkey FOREIGN KEY (organization_id) REFERENCES public.organizations(id)
);
CREATE TABLE public.audit_log (
  id integer NOT NULL DEFAULT nextval('audit_log_id_seq'::regclass),
  account_id integer,
  organization_id integer,
  platform_user_id integer,
  action character varying NOT NULL,
  entity_type character varying,
  entity_id character varying,
  details jsonb,
  ip_address character varying,
  created_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP,
  CONSTRAINT audit_log_pkey PRIMARY KEY (id),
  CONSTRAINT audit_log_account_id_fkey FOREIGN KEY (account_id) REFERENCES public.accounts(id),
  CONSTRAINT audit_log_organization_id_fkey FOREIGN KEY (organization_id) REFERENCES public.organizations(id),
  CONSTRAINT audit_log_platform_user_id_fkey FOREIGN KEY (platform_user_id) REFERENCES public.platform_users(id)
);
CREATE TABLE public.generated_reports (
  id integer NOT NULL DEFAULT nextval('generated_reports_id_seq'::regclass),
  organization_id integer NOT NULL,
  report_month character varying NOT NULL,
  report_year integer NOT NULL,
  organization_data jsonb,
  file_path character varying,
  file_url character varying,
  pdf_generated_at timestamp without time zone,
  status character varying DEFAULT 'active'::character varying,
  generated_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP,
  created_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP,
  updated_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP,
  llm_data jsonb,
  report_type character varying CHECK (report_type::text = ANY (ARRAY['monthly'::character varying, 'quarterly'::character varying]::text[])),
  CONSTRAINT generated_reports_pkey PRIMARY KEY (id),
  CONSTRAINT generated_reports_organization_fkey FOREIGN KEY (organization_id) REFERENCES public.organizations(id)
);
CREATE TABLE public.integration_credentials (
  id integer NOT NULL DEFAULT nextval('integration_credentials_id_seq'::regclass),
  account_id integer,
  credentials jsonb,
  is_active boolean DEFAULT true,
  last_synced timestamp without time zone,
  created_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP,
  updated_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP,
  CONSTRAINT integration_credentials_pkey PRIMARY KEY (id),
  CONSTRAINT integration_credentials_account_id_fkey FOREIGN KEY (account_id) REFERENCES public.accounts(id)
);
CREATE TABLE public.integrations (
  id integer NOT NULL DEFAULT nextval('integrations_id_seq'::regclass),
  integration_key character varying NOT NULL UNIQUE,
  integration_display_name character varying NOT NULL,
  description text,
  integration_fields jsonb,
  is_active boolean DEFAULT true,
  created_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP,
  updated_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP,
  json_object_name text NOT NULL,
  CONSTRAINT integrations_pkey PRIMARY KEY (id)
);
CREATE TABLE public.license_sku_mappings (
  id integer NOT NULL DEFAULT nextval('license_sku_mappings_id_seq'::regclass),
  service_plan_name character varying NOT NULL UNIQUE,
  product_display_name character varying NOT NULL,
  created_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP,
  updated_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP,
  CONSTRAINT license_sku_mappings_pkey PRIMARY KEY (id)
);
CREATE TABLE public.m365_compliance_snapshots (
  id integer NOT NULL DEFAULT nextval('m365_compliance_snapshots_id_seq'::regclass),
  organization_id integer,
  status character varying,
  score_percentage integer,
  total_policies integer,
  policies_data jsonb,
  checked_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP,
  breakdown jsonb,
  title character varying DEFAULT 'Microsoft 365 Compliance Status'::character varying,
  CONSTRAINT m365_compliance_snapshots_pkey PRIMARY KEY (id),
  CONSTRAINT m365_compliance_snapshots_organization_id_fkey FOREIGN KEY (organization_id) REFERENCES public.organizations(id)
);
CREATE TABLE public.m365_credentials (
  id integer NOT NULL DEFAULT nextval('m365_credentials_id_seq'::regclass),
  organization_id integer UNIQUE,
  tenant_id character varying NOT NULL,
  client_id character varying NOT NULL UNIQUE,
  client_secret character varying NOT NULL,
  credential_status character varying DEFAULT 'Active'::character varying,
  last_token_refresh timestamp without time zone,
  created_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP,
  updated_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP,
  account_id integer,
  CONSTRAINT m365_credentials_pkey PRIMARY KEY (id),
  CONSTRAINT m365_credentials_organization_id_fkey FOREIGN KEY (organization_id) REFERENCES public.organizations(id),
  CONSTRAINT m365_credentials_account_id_fkey FOREIGN KEY (account_id) REFERENCES public.accounts(id)
);
CREATE TABLE public.m365_license_snapshots (
  id integer NOT NULL DEFAULT nextval('m365_license_snapshots_id_seq'::regclass),
  organization_id integer,
  total_users integer,
  others_count integer DEFAULT 0,
  standard_count integer DEFAULT 0,
  premium_count integer DEFAULT 0,
  basic_count integer DEFAULT 0,
  license_details jsonb,
  snapshot_date timestamp without time zone DEFAULT CURRENT_TIMESTAMP,
  CONSTRAINT m365_license_snapshots_pkey PRIMARY KEY (id),
  CONSTRAINT m365_license_snapshots_organization_id_fkey FOREIGN KEY (organization_id) REFERENCES public.organizations(id)
);
CREATE TABLE public.m365_mfa_snapshots (
  id integer NOT NULL DEFAULT nextval('m365_mfa_snapshots_id_seq'::regclass),
  organization_id integer,
  percentage numeric,
  status character varying,
  total_users integer,
  mfa_enabled integer,
  mfa_disabled integer,
  mfa_registered integer,
  conditional_access integer DEFAULT 0,
  security_defaults integer DEFAULT 0,
  per_user_mfa integer DEFAULT 0,
  recommendation text,
  description text,
  measurement_date timestamp without time zone,
  CONSTRAINT m365_mfa_snapshots_pkey PRIMARY KEY (id),
  CONSTRAINT m365_mfa_snapshots_organization_id_fkey FOREIGN KEY (organization_id) REFERENCES public.organizations(id)
);
CREATE TABLE public.m365_risky_signins (
  id integer NOT NULL DEFAULT nextval('m365_risky_signins_id_seq'::regclass),
  organization_id integer,
  event_id character varying NOT NULL UNIQUE,
  user_display_name character varying,
  user_id character varying,
  user_principal_name character varying,
  ip_address character varying,
  client_app_used character varying,
  correlation_id character varying,
  conditional_access_status character varying,
  applied_conditional_access_policies jsonb,
  is_interactive boolean,
  device_detail jsonb,
  location jsonb,
  risk_detail character varying,
  risk_level_aggregated character varying,
  risk_level_during_signin character varying,
  risk_state character varying,
  risk_event_types ARRAY,
  risk_event_types_v2 ARRAY,
  resource_display_name character varying,
  resource_id character varying,
  status jsonb,
  app_display_name character varying,
  app_id character varying,
  created_date_time timestamp without time zone,
  last_synced timestamp without time zone DEFAULT CURRENT_TIMESTAMP,
  CONSTRAINT m365_risky_signins_pkey PRIMARY KEY (id),
  CONSTRAINT m365_risky_signins_organization_id_fkey FOREIGN KEY (organization_id) REFERENCES public.organizations(id)
);
CREATE TABLE public.m365_risky_users (
  id integer NOT NULL DEFAULT nextval('m365_risky_users_id_seq'::regclass),
  organization_id integer,
  user_id character varying NOT NULL,
  user_principal_name character varying,
  display_name character varying,
  risk_level character varying,
  risk_state character varying,
  risk_detail character varying,
  risk_last_updated timestamp without time zone,
  is_deleted boolean DEFAULT false,
  is_processing boolean DEFAULT false,
  detected_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP,
  resolved_at timestamp without time zone,
  remediation_action character varying,
  CONSTRAINT m365_risky_users_pkey PRIMARY KEY (id),
  CONSTRAINT m365_risky_users_organization_id_fkey FOREIGN KEY (organization_id) REFERENCES public.organizations(id)
);
CREATE TABLE public.m365_secure_score_history (
  id integer NOT NULL DEFAULT nextval('m365_secure_score_history_id_seq'::regclass),
  organization_id integer,
  current_score numeric,
  max_score numeric,
  percentage numeric,
  active_user_count integer,
  licensed_user_count integer,
  top_improvement_actions jsonb,
  all_improvement_actions jsonb,
  completed_actions jsonb,
  created_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP,
  score_data jsonb,
  CONSTRAINT m365_secure_score_history_pkey PRIMARY KEY (id),
  CONSTRAINT m365_secure_score_history_organization_id_fkey FOREIGN KEY (organization_id) REFERENCES public.organizations(id)
);
CREATE TABLE public.m365_security_alerts (
  id integer NOT NULL DEFAULT nextval('m365_security_alerts_id_seq'::regclass),
  organization_id integer,
  alert_id character varying NOT NULL UNIQUE,
  alert_type character varying,
  title character varying,
  description text,
  severity character varying,
  status character varying,
  category character varying,
  created_at timestamp without time zone,
  last_updated timestamp without time zone,
  service_source character varying,
  affected_user character varying,
  ip_address character varying,
  location jsonb,
  raw_data jsonb,
  CONSTRAINT m365_security_alerts_pkey PRIMARY KEY (id),
  CONSTRAINT m365_security_alerts_organization_id_fkey FOREIGN KEY (organization_id) REFERENCES public.organizations(id)
);
CREATE TABLE public.m365_user_details (
  id integer NOT NULL DEFAULT nextval('m365_user_details_id_seq'::regclass),
  licenses ARRAY,
  mailbox_size_mb integer,
  mailbox_quota_mb integer,
  mailbox_usage_percentage numeric,
  mailbox_items_count integer,
  mailbox_archived_items_count integer,
  onedrive_size_mb integer,
  onedrive_quota_mb integer,
  onedrive_usage_percentage numeric,
  onedrive_files_count integer,
  teams_calls_minutes_last_30_days integer DEFAULT 0,
  teams_meetings_count_last_30_days integer DEFAULT 0,
  teams_messages_count_last_30_days integer DEFAULT 0,
  email_sent_count_last_30_days integer DEFAULT 0,
  documents_edited_last_30_days integer DEFAULT 0,
  risk_level character varying,
  sign_in_attempts_last_30_days integer,
  blocked_sign_in_attempts integer,
  authentication_methods ARRAY,
  last_password_change timestamp without time zone,
  last_sign_in timestamp without time zone,
  groups ARRAY,
  last_updated timestamp without time zone DEFAULT CURRENT_TIMESTAMP,
  user_id character varying,
  CONSTRAINT m365_user_details_pkey PRIMARY KEY (id),
  CONSTRAINT fk_m365_user_details_user_id FOREIGN KEY (user_id) REFERENCES public.m365_users(user_id)
);
CREATE TABLE public.m365_user_devices (
  id integer NOT NULL DEFAULT nextval('m365_user_devices_id_seq'::regclass),
  device_id character varying NOT NULL,
  device_name character varying,
  device_type character varying,
  last_synced timestamp without time zone DEFAULT CURRENT_TIMESTAMP,
  user_id character varying,
  CONSTRAINT m365_user_devices_pkey PRIMARY KEY (id),
  CONSTRAINT fk_m365_user_devices_user_id FOREIGN KEY (user_id) REFERENCES public.m365_users(user_id)
);
CREATE TABLE public.m365_users (
  id integer NOT NULL DEFAULT nextval('m365_users_id_seq'::regclass),
  organization_id integer,
  user_id character varying NOT NULL UNIQUE,
  display_name character varying,
  email character varying,
  department character varying,
  role character varying,
  status character varying,
  mfa_enabled boolean DEFAULT false,
  user_principal_name character varying,
  last_synced timestamp without time zone DEFAULT CURRENT_TIMESTAMP,
  user_type character varying DEFAULT 'Member'::character varying,
  CONSTRAINT m365_users_pkey PRIMARY KEY (id),
  CONSTRAINT m365_users_organization_id_fkey FOREIGN KEY (organization_id) REFERENCES public.organizations(id)
);
CREATE TABLE public.organization_integrations (
  id integer NOT NULL DEFAULT nextval('organization_integrations_id_seq'::regclass),
  organization_id integer NOT NULL,
  integration_id integer NOT NULL,
  platform_organization_id character varying NOT NULL,
  is_active boolean DEFAULT true,
  last_synced timestamp without time zone,
  created_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP,
  updated_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP,
  CONSTRAINT organization_integrations_pkey PRIMARY KEY (id),
  CONSTRAINT organization_integrations_org_fkey FOREIGN KEY (organization_id) REFERENCES public.organizations(id),
  CONSTRAINT organization_integrations_integration_fkey FOREIGN KEY (integration_id) REFERENCES public.integrations(id)
);
CREATE TABLE public.organization_pocs (
  id integer NOT NULL DEFAULT nextval('organization_pocs_id_seq'::regclass),
  organization_id integer NOT NULL,
  poc_name character varying NOT NULL,
  poc_email character varying NOT NULL UNIQUE,
  poc_role character varying,
  created_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP,
  updated_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP,
  is_active boolean NOT NULL DEFAULT true,
  CONSTRAINT organization_pocs_pkey PRIMARY KEY (id),
  CONSTRAINT organization_pocs_organization_id_fkey FOREIGN KEY (organization_id) REFERENCES public.organizations(id)
);
CREATE TABLE public.organizations (
  id integer NOT NULL DEFAULT nextval('organizations_id_seq'::regclass),
  account_id integer,
  organization_name character varying NOT NULL,
  domain character varying,
  industry character varying,
  organization_size character varying,
  status character varying DEFAULT 'Active'::character varying,
  created_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP,
  updated_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP,
  CONSTRAINT organizations_pkey PRIMARY KEY (id),
  CONSTRAINT organizations_account_id_fkey FOREIGN KEY (account_id) REFERENCES public.accounts(id)
);
CREATE TABLE public.platform_available_charts (
  id integer NOT NULL DEFAULT nextval('platform_available_charts_id_seq'::regclass),
  integration_id integer NOT NULL,
  chart_key character varying NOT NULL,
  chart_display_name character varying NOT NULL,
  chart_description text,
  chart_type character varying,
  json_path character varying,
  created_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP,
  CONSTRAINT platform_available_charts_pkey PRIMARY KEY (id),
  CONSTRAINT platform_available_charts_integration_fkey FOREIGN KEY (integration_id) REFERENCES public.integrations(id)
);
CREATE TABLE public.platform_users (
  id integer NOT NULL DEFAULT nextval('platform_users_id_seq'::regclass),
  account_id integer,
  email character varying,
  full_name character varying,
  role character varying NOT NULL,
  is_active boolean DEFAULT true,
  created_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP,
  last_login timestamp without time zone,
  auth_user_id uuid UNIQUE,
  CONSTRAINT platform_users_pkey PRIMARY KEY (id),
  CONSTRAINT platform_users_account_id_fkey FOREIGN KEY (account_id) REFERENCES public.accounts(id),
  CONSTRAINT platform_users_auth_user_id_fkey FOREIGN KEY (auth_user_id) REFERENCES auth.users(id)
);
