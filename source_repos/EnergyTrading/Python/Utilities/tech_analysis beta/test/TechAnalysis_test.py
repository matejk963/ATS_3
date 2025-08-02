from Utilities.tech_analysis import tech_analysis_manager


markets = ['de', 'fr']
inst = tech_analysis_manager(markets=markets)
spread_legs = ['DE_B_M_3_25', 'DE_B_M_4_25']
leg_weights:list = [1, -1],
columns_to_fetch = ['datetime', 'settlement_price']
leg_test = inst.get_leg(contract=spread_legs[0],
                        columns_to_fetch=columns_to_fetch)
spread_test = inst.get_spread(spread_legs=spread_legs,
                            leg_weights=leg_test)