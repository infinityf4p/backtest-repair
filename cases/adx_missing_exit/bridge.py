"""Compatibility only: original calculation methods execute unchanged."""
from strategy import ADXMomentun

class CompatibleADX(ADXMomentun):
    INTERFACE_VERSION = 3
    timeframe = ADXMomentun.ticker_interval

    def populate_indicators(self, dataframe, metadata):
        return super().populate_indicators(dataframe)

    def populate_buy_trend(self, dataframe, metadata):
        return super().populate_buy_trend(dataframe)

    def populate_sell_trend(self, dataframe, metadata):
        return super().populate_sell_trend(dataframe)

    def populate_entry_trend(self, dataframe, metadata):
        return super().populate_buy_trend(dataframe).rename(columns={"buy": "enter_long"})

    def populate_exit_trend(self, dataframe, metadata):
        return super().populate_sell_trend(dataframe).rename(columns={"sell": "exit_long"})
