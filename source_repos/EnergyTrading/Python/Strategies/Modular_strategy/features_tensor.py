import torch
import abc

class TensorDataWrapper():
    def __init__(self, 
                D:torch.TensorType, 
                data_columns:list,
                thold_columns:list,
                X_list: list):
        if D.shape[-1] != len(data_columns):
            raise ValueError(f"dataset D shape[-1] ({D.shape}) doesn't match with number of defined columns({len(data_columns)})")
        self.data_columns = data_columns
        self.thold_columns = thold_columns
        self.D = D
        self.X_list = X_list

class TensorFeature(abc.ABC):
    @abc.abstractmethod
    def condition_short(cls, tdw: TensorDataWrapper):
        pass

    @abc.abstractmethod
    def condition_short(cls, tdw: TensorDataWrapper):
        pass

class FeatureSparsity(TensorFeature):
    data_columns = ['a_price_sparsity', 'b_price_sparsity']
    thold_columns = ['th_feat_sp_dense', 'th_feat_sp_sparse']
    @classmethod
    def condition_short(cls, tdw: TensorDataWrapper):
        idx_ask = tdw.data_columns.index(cls.data_columns[0])
        idx_bid = tdw.data_columns.index(cls.data_columns[1])
        idx_dense = tdw.thold_columns.index(cls.thold_columns[0])
        idx_sparse = tdw.thold_columns.index(cls.thold_columns[1])
        #print(idx_ask, idx_bid, idx_dense, idx_sparse)

        bool_dense = tdw.D[:, idx_ask].unsqueeze(1) < tdw.X_list[idx_dense].unsqueeze(0)
        bool_sparse = tdw.D[:, idx_bid].unsqueeze(1) > tdw.X_list[idx_sparse].unsqueeze(0)

        return [bool_dense, bool_sparse] # shape (D.rows, n-tholds, )
    
    @classmethod
    def condition_long(cls, tdw: TensorDataWrapper):
        idx_ask = tdw.data_columns.index(cls.data_columns[0])
        idx_bid = tdw.data_columns.index(cls.data_columns[1])
        idx_dense = tdw.thold_columns.index(cls.thold_columns[0])
        idx_sparse = tdw.thold_columns.index(cls.thold_columns[1])
        #print(idx_ask, idx_bid, idx_dense, idx_sparse)
        
        bool_sparse = tdw.D[:, idx_ask].unsqueeze(1) > tdw.X_list[idx_sparse].unsqueeze(0)
        bool_dense = tdw.D[:, idx_bid].unsqueeze(1) < tdw.X_list[idx_dense].unsqueeze(0)

        return [bool_dense, bool_sparse] # shape (D.rows, n-tholds, )

class FeatureScaledSp(TensorFeature):
    data_columns = ['scaled_sparsity']
    thold_columns = ['th_feat_scaled_sp']
    @classmethod
    def condition_short(cls, tdw: TensorDataWrapper):
        idx_scaled_sp = tdw.data_columns.index(cls.data_columns[0])
        idx_thold = tdw.thold_columns.index(cls.thold_columns[0])
        #print(idx_scaled_sp, idx_thold)
        
        bool_values = tdw.D[:, idx_scaled_sp].unsqueeze(1) < -tdw.X_list[idx_thold]

        return bool_values
    
    @classmethod
    def condition_long(cls, tdw: TensorDataWrapper):
        idx_scaled_sp = tdw.data_columns.index(cls.data_columns[0])
        idx_thold = tdw.thold_columns.index(cls.thold_columns[0])
        #print(idx_scaled_sp, idx_thold)
        
        bool_values = tdw.D[:, idx_scaled_sp].unsqueeze(1) > tdw.X_list[idx_thold]

        return bool_values

class FeatureIntensity(TensorFeature):
    data_columns = ['int']
    thold_columns = ['th_feat_intensity']
    @classmethod
    def condition_short(cls, tdw: TensorDataWrapper):
        idx_int = tdw.data_columns.index(cls.data_columns[0])
        idx_thold = tdw.thold_columns.index(cls.thold_columns[0])
        #print(idx_int, idx_thold)
        
        bool_values = tdw.D[:, idx_int].unsqueeze(1) > tdw.X_list[idx_thold]

        return bool_values
    
    @classmethod
    def condition_long(cls, tdw: TensorDataWrapper):
        idx_int = tdw.data_columns.index(cls.data_columns[0])
        idx_thold = tdw.thold_columns.index(cls.thold_columns[0])
        #print(idx_int, idx_thold)
        
        bool_values = tdw.D[:, idx_int].unsqueeze(1) > tdw.X_list[idx_thold]

        return bool_values

class FeatureBAVolRat(TensorFeature):
    data_columns = ['ba_volrat_00', 'ba_volrat_30']
    thold_columns = ['th_feat_ba_volrat_00', 'th_feat_ba_volrat_30']
    @classmethod
    def condition_short(cls, tdw: TensorDataWrapper):
        idxs_ba = [i for i, v in enumerate(tdw.data_columns) if v in cls.data_columns]
        idxs_thold = [i for i, v in enumerate(tdw.thold_columns) if v in cls.thold_columns]
        #print(idxs_ba, idxs_thold)
        
        bool_values = [tdw.D[:, i_ba].unsqueeze(1) > tdw.X_list[i_t] for i_t, i_ba in zip(idxs_thold, idxs_ba)]

        return bool_values
    
    @classmethod
    def condition_long(cls, tdw: TensorDataWrapper):
        idxs_ba = [i for i, v in enumerate(tdw.data_columns) if v in cls.data_columns]
        idxs_thold = [i for i, v in enumerate(tdw.thold_columns) if v in cls.thold_columns]
        #print(idxs_ba, idxs_thold)
        
        bool_values = [tdw.D[:, i_ba].unsqueeze(1) < tdw.X_list[i_t] for i_t, i_ba in zip(idxs_thold, idxs_ba)]

        return bool_values
    

class FeatureActionAbsSum(TensorFeature):
    data_columns = ['action_abs_sum_1s', 'action_abs_sum_5s']
    thold_columns = ['th_feat_action_abs_sum_1s', 'th_feat_action_abs_sum_5s']
    @classmethod
    def condition_short(cls, tdw: TensorDataWrapper):
        idxs_action = [i for i, v in enumerate(tdw.data_columns) if v in cls.data_columns]
        idxs_thold = [i for i, v in enumerate(tdw.thold_columns) if v in cls.thold_columns]
        #print(idxs_ba, idxs_thold)
        
        bool_values = [tdw.D[:, i_act].unsqueeze(1) > tdw.X_list[i_t] for i_t, i_act in zip(idxs_thold, idxs_action)]

        return bool_values
    
    @classmethod
    def condition_long(cls, tdw: TensorDataWrapper):
        idxs_action = [i for i, v in enumerate(tdw.data_columns) if v in cls.data_columns]
        idxs_thold = [i for i, v in enumerate(tdw.thold_columns) if v in cls.thold_columns]
        #print(idxs_ba, idxs_thold)
        
        bool_values = [tdw.D[:, i_act].unsqueeze(1) > tdw.X_list[i_t] for i_t, i_act in zip(idxs_thold, idxs_action)]

        return bool_values
    

class FeatureActionSum(TensorFeature):
    data_columns = ['action_sum_1s', 'action_sum_5s']
    thold_columns = ['th_feat_action_sum_1s', 'th_feat_action_sum_5s']
    @classmethod
    def condition_short(cls, tdw: TensorDataWrapper):
        idxs_action = [i for i, v in enumerate(tdw.data_columns) if v in cls.data_columns]
        idxs_thold = [i for i, v in enumerate(tdw.thold_columns) if v in cls.thold_columns]
        #print(idxs_ba, idxs_thold)
        
        bool_values = [tdw.D[:, i_act].unsqueeze(1) > tdw.X_list[i_t] for i_t, i_act in zip(idxs_thold, idxs_action)]

        return bool_values
    
    @classmethod
    def condition_long(cls, tdw: TensorDataWrapper):
        idxs_action = [i for i, v in enumerate(tdw.data_columns) if v in cls.data_columns]
        idxs_thold = [i for i, v in enumerate(tdw.thold_columns) if v in cls.thold_columns]
        #print(idxs_ba, idxs_thold)
        
        bool_values = [tdw.D[:, i_act].unsqueeze(1) < -tdw.X_list[i_t] for i_t, i_act in zip(idxs_thold, idxs_action)]

        return bool_values
    
class FeatureBODiff(TensorFeature):
    data_columns = ['diff_b_price', 'diff_a_price']
    thold_columns = ['th_feat_bo_diff']
    @classmethod
    def condition_short(cls, tdw: TensorDataWrapper):
        idx_ask = tdw.data_columns.index(cls.data_columns[1])
        idx_thold = tdw.thold_columns.index(cls.thold_columns[0])
        #print(idx_level, idx_thold)
        
        bool_values = tdw.D[:, idx_ask].unsqueeze(1) < tdw.X_list[idx_thold]

        return bool_values
    
    @classmethod
    def condition_long(cls, tdw: TensorDataWrapper):
        idx_bid = tdw.data_columns.index(cls.data_columns[0])
        idx_thold = tdw.thold_columns.index(cls.thold_columns[0])
        #print(idx_level, idx_thold)
        
        bool_values = tdw.D[:, idx_bid].unsqueeze(1) > tdw.X_list[idx_thold]

        return bool_values

class FeatureOrderT1(TensorFeature):
    data_columns = ['bid_t1', 'ask_t1']
    thold_columns = ['th_feat_order_t1']
    @classmethod
    def condition_short(cls, tdw: TensorDataWrapper):
        idx_bid = tdw.data_columns.index(cls.data_columns[0])
        #print(idx_bid)
        
        bool_values = tdw.D[:, idx_bid].unsqueeze(1)

        return bool_values
    
    @classmethod
    def condition_long(cls, tdw: TensorDataWrapper):
        idx_ask = tdw.data_columns.index(cls.data_columns[1])
        #print(idx_ask)
        
        bool_values = tdw.D[:, idx_ask].unsqueeze(1)

        return bool_values


class FeatureTrdGap(TensorFeature):
    data_columns = ['trd_gap']
    thold_columns = ['th_feat_trd_gap']
    @classmethod
    def condition_short(cls, tdw: TensorDataWrapper):
        idx_margin = tdw.data_columns.index(cls.data_columns[0])
        idx_thold = tdw.thold_columns.index(cls.thold_columns[0])
        #print(idx_level, idx_thold)
        
        bool_values = tdw.D[:, idx_margin].unsqueeze(1) < -tdw.X_list[idx_thold]

        return bool_values
    
    @classmethod
    def condition_long(cls, tdw: TensorDataWrapper):
        idx_margin = tdw.data_columns.index(cls.data_columns[0])
        idx_thold = tdw.thold_columns.index(cls.thold_columns[0])
        #print(idx_level, idx_thold)
        
        bool_values = tdw.D[:, idx_margin].unsqueeze(1) > tdw.X_list[idx_thold]

        return bool_values
    
    
    
class FeatureFarLevel(TensorFeature):
    data_columns = ['_far_level']
    thold_columns = ['th_feat_far_level']
    @classmethod
    def condition_short(cls, tdw: TensorDataWrapper):
        idx_level = tdw.data_columns.index(cls.data_columns[0])
        idx_thold = tdw.thold_columns.index(cls.thold_columns[0])
        #print(idx_level, idx_thold)
        
        bool_values = tdw.D[:, idx_level].unsqueeze(1) > (1 - tdw.X_list[idx_thold])

        return bool_values
    
    @classmethod
    def condition_long(cls, tdw: TensorDataWrapper):
        idx_level = tdw.data_columns.index(cls.data_columns[0])
        idx_thold = tdw.thold_columns.index(cls.thold_columns[0])
        #print(idx_level, idx_thold)
        
        bool_values = tdw.D[:, idx_level].unsqueeze(1) < tdw.X_list[idx_thold]

        return bool_values

class FeatureIntervalInt(TensorFeature):
    data_columns = ['interval_int']
    thold_columns = ['th_feat_interval_int']
    @classmethod
    def condition_short(cls, tdw: TensorDataWrapper):
        idx_int = tdw.data_columns.index(cls.data_columns[0])
        idx_thold = tdw.thold_columns.index(cls.thold_columns[0])
        #print(idx_level, idx_thold)
        
        bool_values = tdw.D[:, idx_int].unsqueeze(1) > tdw.X_list[idx_thold]

        return bool_values
    
    @classmethod
    def condition_long(cls, tdw: TensorDataWrapper):
        idx_int = tdw.data_columns.index(cls.data_columns[0])
        idx_thold = tdw.thold_columns.index(cls.thold_columns[0])
        #print(idx_level, idx_thold)
        
        bool_values = tdw.D[:, idx_int].unsqueeze(1) > tdw.X_list[idx_thold]

        return bool_values

class FeatureIntervalPdiff(TensorFeature):
    data_columns = ['interval_pdiff']
    thold_columns = ['th_feat_interval_pdiff']
    @classmethod
    def condition_short(cls, tdw: TensorDataWrapper):
        idx_pdiff = tdw.data_columns.index(cls.data_columns[0])
        idx_thold = tdw.thold_columns.index(cls.thold_columns[0])
        #print(idx_level, idx_thold)
        
        bool_values = tdw.D[:, idx_pdiff].unsqueeze(1) < -tdw.X_list[idx_thold]

        return bool_values
    
    @classmethod
    def condition_long(cls, tdw: TensorDataWrapper):
        idx_pdiff = tdw.data_columns.index(cls.data_columns[0])
        idx_thold = tdw.thold_columns.index(cls.thold_columns[0])
        #print(idx_level, idx_thold)
        
        bool_values = tdw.D[:, idx_pdiff].unsqueeze(1) > tdw.X_list[idx_thold]

        return bool_values
    


class FeaturePMovement(TensorFeature):
    data_columns = ['p_movement_0.3']
    thold_columns = ['th_feat_p_movement03']
    @classmethod
    def condition_short(cls, tdw: TensorDataWrapper):
        idx_pa = tdw.data_columns.index(cls.data_columns[0])
        idx_thold = tdw.thold_columns.index(cls.thold_columns[0])
        #print(idx_pa, idx_thold)
        
        bool_values = tdw.D[:, idx_pa].unsqueeze(1) < -tdw.X_list[idx_thold]

        return bool_values
    
    @classmethod
    def condition_long(cls, tdw: TensorDataWrapper):
        idx_pa = tdw.data_columns.index(cls.data_columns[0])
        idx_thold = tdw.thold_columns.index(cls.thold_columns[0])
        #print(idx_pa, idx_thold)
        
        bool_values = tdw.D[:, idx_pa].unsqueeze(1) > tdw.X_list[idx_thold]

        return bool_values
    
class FeatureBASpread(TensorFeature):
    data_columns = ['ba_spread']
    thold_columns = ['th_feat_ba_spread']
    @classmethod
    def condition_short(cls, tdw: TensorDataWrapper):
        idx_pa = tdw.data_columns.index(cls.data_columns[0])
        idx_thold = tdw.thold_columns.index(cls.thold_columns[0])
        #print(idx_pa, idx_thold)
        
        bool_values = tdw.D[:, idx_pa].unsqueeze(1) < tdw.X_list[idx_thold]

        return bool_values
    
    @classmethod
    def condition_long(cls, tdw: TensorDataWrapper):
        idx_pa = tdw.data_columns.index(cls.data_columns[0])
        idx_thold = tdw.thold_columns.index(cls.thold_columns[0])
        #print(idx_pa, idx_thold)
        
        bool_values = tdw.D[:, idx_pa].unsqueeze(1) < tdw.X_list[idx_thold]

        return bool_values
               

# data_columns = ['ba_spread', 'intensity', 'fair_margin']

# thold_vectors = {
#     'th_ba_spread': [0.21, 0.41, 1.0],
#     'th_intensity': [0.0, 1.0, 2.0, 3.0],
#     'th_fair_margin': [-.01, 0.0, 0.05, 0.1, 0.15]
# }
# D_list = [ for thold in thold_vectors.values()]
# D = torch.rand(size=(100, len(data_columns)))
# p_grid = torch.cartesian_prod(thold_vectors.values())
