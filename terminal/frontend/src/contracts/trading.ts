export const MARKET_SIDES = ["Buy", "Sell"] as const;
export const VOLUME_UNITS = ["working_volume", "usdt"] as const;
export const SLIPPAGE_TYPES = ["TickSize", "Percent"] as const;
export const POSITION_SIDES = ["Flat", "Long", "Short"] as const;
export const TIME_IN_FORCE_VALUES = ["GTC"] as const;
export const HANDLED_REASON_CODES = ["insufficient_sizing_precision"] as const;

export type MarketSide = (typeof MARKET_SIDES)[number];
export type VolumeUnit = (typeof VOLUME_UNITS)[number];

export type VolumeRequest = {
  unit: VolumeUnit;
  amount: string;
};

export type MarketCommandRequest = {
  client_action_id: string;
  symbol: string;
  side: MarketSide;
  volume: VolumeRequest;
  sizing_reference_price: string;
  slippage_type: (typeof SLIPPAGE_TYPES)[number];
  slippage_value: string;
};

export type LiveMarketCommandRequest = MarketCommandRequest & {
  account_id: string;
  session_generation: number;
};

export type LiveMarketCommandResponse = {
  status: "accepted_pending" | "completed" | "blocked" | "rejected" | "unknown";
  reason_code: string;
  command_id: string | null;
  order_link_id: string | null;
  reconciliation_required: boolean;
};

export type FullCloseCommandRequest = {
  client_action_id: string;
  symbol: string;
};

export type CloseAllCommandRequest = {
  client_action_id: string;
};

export type PaperOpenPosition = {
  symbol: string;
  position_side: "Long" | "Short";
  position_quantity: string;
  average_entry: string | null;
  engaged_notional_usdt: string;
  engaged_wv: string;
  current_price: string | null;
  unrealized_pnl: string | null;
  tick_size: string;
};

export type CloseAllCommandResponse = {
  ok: boolean;
  client_action_id: string;
  results: CommandResult[];
  positions: PaperOpenPosition[];
};

export type PaperOpenPositionsResponse = {
  ok: boolean;
  account_id: string;
  positions: PaperOpenPosition[];
};

export type LimitCommandRequest = {
  client_action_id: string;
  symbol: string;
  side: MarketSide;
  volume: VolumeRequest;
  sizing_reference_price: string;
  limit_price: string;
  time_in_force: (typeof TIME_IN_FORCE_VALUES)[number];
};

export type PaperLimitCancelRequest = {
  client_action_id: string;
  symbol: string;
  order_id: string;
};

export type PaperLimitAmendRequest = {
  client_action_id: string;
  symbol: string;
  order_id: string;
  limit_price: string;
};

export type PaperLimitOrder = {
  order_id: string;
  order_link_id: string;
  symbol: string;
  side: MarketSide;
  price: string;
  quantity: string;
  time_in_force: (typeof TIME_IN_FORCE_VALUES)[number];
};

export type PaperLimitMutationResult = {
  client_action_id: string;
  status: string;
  reason_code: string;
  order_id: string | null;
};

export type PaperLimitMutationResponse = PaperLimitMutationResult & {
  paper_state: PaperState;
};

export type PaperProtection = {
  status: string;
  take_profit: string | null;
  stop_loss: string | null;
  trailing_stop: string | null;
  pending_command_id: string | null;
  warning: string | null;
  effective_quantity: string | null;
};

export type PaperStopMutationRequest = {
  client_action_id: string;
  symbol: string;
  trigger_price: string;
};

export type PaperStopDeleteRequest = {
  client_action_id: string;
  symbol: string;
};

export type PaperStopMutationResponse = {
  client_action_id: string;
  status: string;
  reason_code: string;
  paper_state: PaperState;
};

export type PaperTakeMutationRequest = PaperStopMutationRequest;
export type PaperTakeDeleteRequest = PaperStopDeleteRequest;
export type PaperTakeMutationResponse = PaperStopMutationResponse;

export type CommandResult = {
  client_action_id: string;
  status: string;
  reason_code: string;
  message: string;
  command_id: string | null;
  reconciliation_required: boolean;
};

export type CommandMutationResponse = CommandResult & {
  paper_state: PaperState;
};

export type PaperState = {
  ok: boolean;
  state_revision: number;
  account_id: string;
  symbol: string;
  initial_deposit_usdt: string;
  equity_usdt: string;
  one_wv_usdt: string;
  position_side: (typeof POSITION_SIDES)[number];
  position_quantity: string;
  average_entry: string | null;
  engaged_notional_usdt: string;
  engaged_wv: string;
  active_limit_orders: PaperLimitOrder[];
  protection?: PaperProtection;
};
