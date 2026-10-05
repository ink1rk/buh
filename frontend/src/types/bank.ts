export interface BankProvider {
  provider: string
  title: string
  supports_statement: boolean
  supports_api: boolean
  statement_formats: string[]
  instructions: string
}

export interface BankConnection {
  id: number
  provider: string
  title: string
  label: string
  account_id: number | null
  account_name: string
  account_balance: number | null
  mode: 'statement' | 'api'
  status: 'idle' | 'syncing' | 'error'
  is_active: boolean
  external_account_id: string
  last_synced_at: string | null
  last_operation_on: string | null
  last_error: string
  imported_total: number
  has_credentials: boolean
}

export interface BankImportRun {
  id: number
  connection_id: number
  source_name: string
  source_kind: 'statement' | 'api'
  status: 'ok' | 'error'
  parsed_count: number
  imported_count: number
  duplicate_count: number
  skipped_count: number
  period_from: string | null
  period_to: string | null
  closing_balance: number | null
  warnings: string[]
  error: string
  created_at: string | null
}
