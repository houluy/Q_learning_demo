import yaml
import pdb
import json

import numpy as np
import random
import pandas as pd
import matplotlib.pyplot as plt
import time
import pathlib

file_path = pathlib.Path(__file__).parent
defaultQfile = file_path / 'Q.csv'
defaultConvfile = file_path / 'conv.csv'

df = pd.DataFrame

class OutOfRangeException(Exception):
    pass

class QFileNotFoundError(OSError):
    pass

class Q:
    def __init__(
        self,
        state_set,
        action_set,
        available_actions,
        reward_func,
        transition_func,
        init,
        ahook=None,
        train_steps=300,
        run=None,
        start_state=None,
        end_states=None,
        start_at=0,
        end_at=[-1],
        config_file=None,
        q_file=defaultQfile,
        conv_file=defaultConvfile,
        load=False,
        custom_params=None,
        epsilon=None,
        gamma=None,
        alpha=None,
        eta=0.9,
        iota=0.9,
        display=True,
        maximum_iteration=200000,
        sleep_time=0,
        heuristic=False,
        quit_mode='c',
    ):
        # Define state and action
        self._state_set = state_set
        if start_state is None:
            self._state_start_at = start_at
            self._state_end_at = end_at
            self._init_state = self._state_set[self._state_start_at]
            self._end_state = [self._state_set[x] for x in self._state_end_at]
        else:
            self._init_state = start_state
            self._end_state = end_states
        self._action_set = action_set
        self._available_actions = available_actions # Map between state and available actions
        self._run = run
        self._init = init
        self.ahook = ahook
        state_len, action_len = len(self._state_set), len(self._action_set)
        self._dimension = (state_len, action_len)
        self._q_file = q_file
        self._conv_file = conv_file
        self._custom_params = custom_params if custom_params else {}
        self._custom_show = self._custom_params.get('show', None)
        self._sleep_time = sleep_time
        self._train_steps = train_steps
        self._display_flag = display
        self._maximum_iteration = maximum_iteration
        self._H_table = self.build_q_table() # Heurisitc algorithm
        self._eta = eta
        self._iota = iota
        # self._hash_lookup_table = {
        #     hash(x): x for x in set(self._state_set + self._action_set)
        # }

        # Reward function
        self._reward_func = reward_func

        # State transition function
        self._transition_func = transition_func

        # Generate Q table
        if load:
            if not self._q_file.is_file():
                raise QFileNotFoundError('Please check if the Q file exists at: {}'.format(q_file))
            self._q_table = self._load_q(file_name=self._q_file)
        else:
            self._q_table = self.build_q_table()

        # Config all the necessary parameters
        if config_file:
            config = yaml.load(open(config_file))
            self._load_config(config=config)
        else:
            self._epsilon = epsilon
            self._gamma = gamma
            self._alpha = alpha

        self.B = 100
        self.A = self._alpha * self.B
        self._heuristic = heuristic
        self._quit_mode = quit_mode

    def _load_config(self, config):
        seq = ['epsilon', 'gamma', 'alpha', 'phi']
        self._epsilon, self._gamma, self._alpha, self._phi = [config.get(x) for x in seq]

    def _load_q(self, file_name=None):
        if file_name is None:
            file_name = self._q_file
        self._q_table = pd.read_csv(file_name, header=None, index_col=False)
        self._q_table.columns = self._action_set
        self._q_table.index = self._state_set
        #self._q_table.columns = self._q_table.columns.astype(tuple)
        return self._q_table

    def _save_q(self):
        self._q_table.to_csv(self._q_file, index=False, header=False)

    def _save_conv(self):
        np.savetxt(self._conv_file, self.conv)

    def _display(self, info=False, sleep=True, state=None):
        if self._display_flag:
            if info is not False:
                self._display_train_info(train_round=info)
            if self._custom_show:
                self._custom_show(state=state)
                if sleep:
                    time.sleep(self._sleep_time)

    def _display_train_info(self, train_round):
        print('train_round: {}'.format(train_round))
        #print('Convergence: {}'.format(self.conv[-1] - self.conv[-2] if len(self.conv) > 1 else self.conv[-1]))
        #print('Q table: {}'.format(self._q_table))

    def build_q_table(self):
        index = self._state_set
        columns = self._action_set
        Q_table = df(
            #np.random.rand(*self._dimension),
            np.zeros(self._dimension),
            index=index,
            columns=columns,
        )
        return Q_table

    @property
    def q_table(self):
        return self._q_table

    def alpha_log(self, itertime):
        return np.log(itertime + 1)/(itertime + 1)

    def alpha_linear(self, itertime):
        return self.A/(self.B + itertime)

    def choose_action(self, state):
        available_actions = self._available_actions(state=state)
        if (len(available_actions) == 1):
            return available_actions[0]
        else:
            #pdb.set_trace()
            all_Q = self._q_table.loc[[state], available_actions]
            if (np.random.uniform() > self._epsilon):
                print('Random')
                action = random.choice(available_actions)
                #action_ind = np.where(self._action_set == action)[0][0] # Actions must be numpy array
            else:
                mval = all_Q.max().max()
                maxQ_actions = all_Q[all_Q == mval].dropna(axis=1).columns
                print('Max actions:{}'.format(maxQ_actions))
                action = np.random.choice(maxQ_actions)
                #if maxQ_actions.size == 1:
                #    action = maxQ_actions.columns.values[0]
                #else:
                #    count = self.move_count.loc[[state], maxQ_actions]
                #    unvis_actions = count[count == 0].dropna(axis=1).columns
                #    action = np.random.choice(unvis_actions)
            return action

    def choose_optimal_action(self, state):
        return self._q_table.loc[[state], :].idxmax(axis=1).values[0]

    def choose_heuristic_action(self, state):
        available_actions = self._available_actions(state=state)
        if (len(available_actions) == 1):
            return available_actions[0]
        else:
            all_Q = self._q_table.loc[[state], :] + self._iota*self._H_table.loc[[state], :]
            if (np.random.uniform() > self._epsilon) or all_Q.all().all():
                action = random.choice(available_actions)
                #action_ind = np.where(self._action_set == action)[0][0] # Actions must be numpy array
            else:
                action = all_Q.idxmax()
            return action
    
    def train(self):
        '''
        conv: If conv is True, then use the self.convergence as the break condition
        '''
        total_step = self._train_steps
        step = 0
        stop = False
        #self._q_table = self.build_q_table()
        self._H_table = self.build_q_table() # Heurisitc algorithm
        init_Q = self._q_table.copy()
        self.conv = np.array([0])
        while not stop:
            self._init()
            self.move_count = self.build_q_table()
            state = self._init_state
            end = False
            self._display(info=step, sleep=False, state=state)
            while not end:
                #pdb.set_trace()
                if not self._heuristic:
                    action = self.choose_action(state=state)
                else:
                    action = self.choose_heuristic_action(state=state)
                q_predict = self._q_table.loc[[state], [action]].values[0][0]
                reward = self._reward_func(state=state, action=action)
                next_state = self._transition_func(state=state, action=action)
                self.move_count.loc[[state], [action]] += 1

                if next_state in self._end_state:
                    q = reward
                    end = True
                else:
                    q = reward + self._gamma * self._q_table.loc[[next_state], :].max().max()
                self._H_table.loc[[state], :] = 0
                self._H_table.loc[[state], [action]] = self._q_table.loc[[state], :].max().max() - self._q_table.loc[[state], [action]] + self._eta
                self._q_table.loc[[state], [action]] += self.alpha_linear(step) * (q - q_predict)
                state = next_state
                self._display(state=state)
            step += 1
            if self._quit_mode == 'c':
                if step >= self._maximum_iteration:
                    raise OutOfRangeException('The iteration time has exceeded the maximum value')
                else:
                    stop = self.convergence(self._q_table.subtract(init_Q))
                    #last_Q = self._q_table.copy()
            else:
                #last_Q = self._q_table.copy()
                self.convergence(self._q_table.subtract(init_Q))
                stop = (step == total_step)
            self._save_q()
            self._save_conv()
        #self.plot_conv()
        if self.ahook:
            self.ahook()
        return self.conv

    def plot_conv(self):
        plt.figure()
        plt.plot(range(len(self.conv)), self.conv)

    def run(self):
        self._run(self.choose_optimal_action)

    def convergence(self, delta_Q=None):
        Q_sum = delta_Q.sum().sum()
        self.conv = np.append(self.conv, Q_sum)
        if self.conv.size > 2 and 0 <= Q_sum - self.conv[-2] < self._phi:
            print('Conv:{}'.format(Q_sum - self.conv[-2]))
            return True
        else:
            return False

    def start(self, mode=True):
        if mode:
            return self.train()
        else:
            return Q.run(self)
