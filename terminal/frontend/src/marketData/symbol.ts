export function baseAssetFromSymbol(symbol: string, quote = "USDT") {
  return symbol.endsWith(quote) && symbol.length > quote.length
    ? symbol.slice(0, -quote.length)
    : symbol;
}
