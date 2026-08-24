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

export type FullCloseCommandRequest = {
  client_action_id: string;
  symbol: string;
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

export type CommandResult = {
  client_action_id: string;
  status: string;
  reason_code: string;
  message: string;
  command_id: string | null;
  reconciliation_required: boolean;
};

export type PaperState = {
  ok: boolean;
  account_id: string;
  symbol: string;
  initial_deposit_usdt: string;
  equity_usdt: string;
  one_wv_usdt: string;
  position_side: (typeof POSITION_SIDES)[number];
  position_quantity: string;
  engaged_notional_usdt: string;
  engaged_wv: string;
  active_limit_orders: PaperLimitOrder[];
};
