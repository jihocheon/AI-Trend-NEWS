"""Shared, validated selection/ranking weights."""
DEFAULT_WEIGHTS={'technical_relevance':.30,'foundational_importance':.25,'practical_utility':.20,
                 'novelty':.08,'credibility':.12,'freshness':.05}


def validate_weights(weights):
    if set(weights)!=set(DEFAULT_WEIGHTS) or any(type(v) not in (int,float) or not 0<=v<=1 for v in weights.values()) or abs(sum(weights.values())-1)>1e-6:
        raise ValueError('Ranking weights must contain the six factor names, be in [0,1], and sum to 1')
    return weights
