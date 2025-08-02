"""In addition to custom strategy, we have to make a template class available"""

from . import custom_strategy
from . import so_strategy_template


template_class = so_strategy_template.StrategyTemplate
