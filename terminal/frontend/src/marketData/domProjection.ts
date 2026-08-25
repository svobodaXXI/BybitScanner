import type {
  MarketSide,
  NormalizedOrderBook,
  PriceLevel,
} from "../contracts/marketData";

export const DOM_LEVELS_PER_SIDE = 8;
export const DOM_VISIBLE_ROWS = DOM_LEVELS_PER_SIDE * 2;
export const DOM_ROW_HEIGHT_REM = 1.36;
export const DOM_COMPRESSION = 5;

export interface DisplayDomLevel extends PriceLevel {
  side: MarketSide | null;
  isBest: boolean;
}

export interface DisplayDomProjection {
  levels: DisplayDomLevel[];
  nativeTickSize: number;
  displayStep: number;
  centerPrice: number | null;
  bestBid: number | null;
  bestAsk: number | null;
}

const pricePrecision = (tickSize: number) => {
  const text = tickSize.toFixed(12).replace(/0+$/, "");
  return Math.max(0, text.length - text.indexOf(".") - 1);
};

const normalizedGridPrice = (
  gridIndex: number,
  tickSize: number,
  compression = DOM_COMPRESSION,
) =>
  Number(
    (gridIndex * tickSize * compression).toFixed(pricePrecision(tickSize)),
  );

export function inferNativeTickSize(book: NormalizedOrderBook): number {
  const differences: number[] = [];
  for (const side of [book.bids, book.asks]) {
    for (let index = 1; index < side.length; index += 1) {
      const difference = Math.abs(side[index - 1].price - side[index].price);
      if (difference > 0) differences.push(difference);
    }
  }
  return differences.length > 0 ? Math.min(...differences) : 0;
}

export function projectPriceToDisplayBucket(
  price: number,
  side: MarketSide,
  tickSize: number,
  compression = DOM_COMPRESSION,
): number {
  const step = tickSize * compression;
  if (!(step > 0)) return price;
  const scaled = price / step;
  const epsilon = 1e-8;
  const bucketIndex =
    side === "BUY" ? Math.floor(scaled + epsilon) : Math.ceil(scaled - epsilon);
  return Number((bucketIndex * step).toFixed(pricePrecision(tickSize)));
}

export function recommendedLadderCenter(
  book: NormalizedOrderBook,
): number | null {
  const tickSize = inferNativeTickSize(book);
  const bestBid = book.bids[0]?.price;
  const bestAsk = book.asks[0]?.price;
  if (!(tickSize > 0) || bestBid === undefined || bestAsk === undefined) {
    return null;
  }
  const bidBucket = projectPriceToDisplayBucket(bestBid, "BUY", tickSize);
  const askBucket = projectPriceToDisplayBucket(bestAsk, "SELL", tickSize);
  const step = tickSize * DOM_COMPRESSION;
  return normalizedGridPrice(
    Math.round((bidBucket + askBucket) / 2 / step),
    tickSize,
  );
}

export function projectDomBook(
  book: NormalizedOrderBook,
  centerPrice: number | null = recommendedLadderCenter(book),
  compression = DOM_COMPRESSION,
): DisplayDomProjection {
  const nativeTickSize = inferNativeTickSize(book);
  const displayStep = nativeTickSize * compression;
  const bestBid = book.bids[0]?.price ?? null;
  const bestAsk = book.asks[0]?.price ?? null;
  if (!(displayStep > 0) || centerPrice === null) {
    return {
      levels: [],
      nativeTickSize,
      displayStep,
      centerPrice,
      bestBid,
      bestAsk,
    };
  }

  const quantities = new Map<number, { side: MarketSide; quantity: number }>();
  const aggregate = (levels: readonly PriceLevel[], side: MarketSide) => {
    for (const level of levels) {
      const price = projectPriceToDisplayBucket(
        level.price,
        side,
        nativeTickSize,
        compression,
      );
      const existing = quantities.get(price);
      quantities.set(price, {
        side,
        quantity: (existing?.quantity ?? 0) + level.quantity,
      });
    }
  };
  aggregate(book.asks, "SELL");
  aggregate(book.bids, "BUY");

  const bestBidBucket =
    bestBid === null
      ? null
      : projectPriceToDisplayBucket(
          bestBid,
          "BUY",
          nativeTickSize,
          compression,
        );
  const bestAskBucket =
    bestAsk === null
      ? null
      : projectPriceToDisplayBucket(
          bestAsk,
          "SELL",
          nativeTickSize,
          compression,
        );
  const centerGridIndex = Math.round(centerPrice / displayStep);
  const topGridIndex = centerGridIndex + DOM_LEVELS_PER_SIDE;
  const levels = Array.from({ length: DOM_VISIBLE_ROWS }, (_, rowIndex) => {
    const price = normalizedGridPrice(
      topGridIndex - rowIndex,
      nativeTickSize,
      compression,
    );
    const liquidity = quantities.get(price);
    return {
      price,
      quantity: liquidity?.quantity ?? 0,
      side: liquidity?.side ?? null,
      isBest: price === bestBidBucket || price === bestAskBucket,
    };
  });

  return {
    levels,
    nativeTickSize,
    displayStep,
    centerPrice: normalizedGridPrice(
      centerGridIndex,
      nativeTickSize,
      compression,
    ),
    bestBid,
    bestAsk,
  };
}

export function displaySweptRows(
  nativeSweptTicks: number,
  compression = DOM_COMPRESSION,
): number {
  return Math.max(1, Math.ceil(nativeSweptTicks / compression));
}

export function priceToLadderRow(
  price: number,
  centerPrice: number,
  tickSize: number,
): number {
  const displayStep = tickSize * DOM_COMPRESSION;
  const topPrice = centerPrice + DOM_LEVELS_PER_SIDE * displayStep;
  return (topPrice - price) / displayStep;
}

export function projectSweepCenterRow(
  book: NormalizedOrderBook,
  lowPrice: number,
  highPrice: number,
  tickSize: number,
  centerPrice: number | null = recommendedLadderCenter(book),
): number | null {
  if (centerPrice === null || !(tickSize > 0)) return null;
  const lowRow = priceToLadderRow(lowPrice, centerPrice, tickSize);
  const highRow = priceToLadderRow(highPrice, centerPrice, tickSize);
  return (lowRow + highRow) / 2 - (DOM_VISIBLE_ROWS - 1) / 2;
}
