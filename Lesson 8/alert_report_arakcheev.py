# coding=utf-8

from datetime import datetime, timedelta
import matplotlib.pyplot as plt
import seaborn as sns
import pandas as pd
import numpy as np
import io
from io import StringIO
import pandahouse as ph
import requests
import telegram

from airflow.decorators import dag, task
from airflow.operators.python import get_current_context


# Дефолтные параметры для тасков
default_args = {
    'owner': 'd-arakcheev',
    'depends_on_past': False,
    'retries': 2,
    'retry_delay': timedelta(minutes=6),
    'start_date': datetime(2023, 3, 25),
}

# Интервал запуска DAG
schedule_interval = '*/15 * * * *'

# Настройки телеграм-бота
my_token = 'ToKeN:01010' 
my_bot = telegram.Bot(token=my_token) # получаем доступ
# my_chat_id = ********

# Функция для clickhouse. Host, user и password заменены.
def ch_get_df(query='Select 1', host='https://*********karpov.courses', user='*****', password='*********'):
    r = requests.post(host, data=query.encode("utf-8"), auth=(user, password), verify=False)
    result = pd.read_csv(StringIO(r.text), sep='\t')
    return result

# Функция для отправки текста в телеграм
# def send_mssg_telegram(my_chat_id, mssg):
    # my_bot.sendMessage(chat_id=my_chat_id, text=mssg)
    # print('Сообщение успешно отправлено')
    
# Функция для фото/изображений в телеграм
def send_img_telegram(my_chat_id, img, msg):
    my_bot.sendPhoto(chat_id=my_chat_id, photo=img, caption=msg)
    print('Изображение успешно отправлено')

# Функция для проверки аномалий
def check_anomaly(df_copy, metric, n=4, a=1.5):
    df_copy['q25'] = df_copy[metric].shift(1).rolling(n).quantile(0.25)
    df_copy['q75'] = df_copy[metric].shift(1).rolling(n).quantile(0.75)
    df_copy['iqr'] = df_copy['q75'] - df_copy['q25']
    df_copy['high'] = df_copy['q75'] + a * df_copy['iqr']
    df_copy['low'] = df_copy['q25'] - a * df_copy['iqr']

    df_copy['high'] = df_copy['high'].rolling(n, center=True).mean()
    df_copy['low'] = df_copy['low'].rolling(n, center=True).mean()
    
    if df_copy[metric].iloc[-1] < df_copy['low'].iloc[-1] or df_copy[metric].iloc[-1] > df_copy['high'].iloc[-1]:
        is_alert = 1
    else:
        is_alert = 0

    return is_alert, df_copy
    

# Функция для активации алертов
def run_alert(df, metrics):
    my_chat_id = ********
    
    for metric in metrics:
        print(metric)
        df_copy = df[['ts', 'date', 'hm', metric]].copy()
        is_alert, df_copy = check_anomaly(df_copy, metric)
        
        if is_alert == 1:
            print(f'Есть алерт по метрике {metric}.')
            metric = metric
            current_val = df_copy[metric].iloc[-1]
            last_val_diff = 1 - (df_copy[metric].iloc[-1] / df_copy[metric].iloc[-2])
            msg = f'Метрика {metric}: \n текущее значение {current_val:.2f} \n отклонение от предыдущего значения {last_val_diff:.2%}.'
            
            sns.set(rc={'figure.figsize': (20, 15)})
            plt.tight_layout()

            ax = sns.lineplot(x=df_copy['ts'], y=df_copy[metric], label='metric')
            ax = sns.lineplot(x=df_copy['ts'], y=df_copy['high'], label='high')
            ax = sns.lineplot(x=df_copy['ts'], y=df_copy['low'], label='low')

            for ind, label in enumerate(ax.get_xticklabels()):
                if ind % 30 == 0:
                    label.set_visible(True)
                else:
                    label.set_visible(False)
            ax.set(xlabel='time')
            ax.set(ylabel=metric)

            ax.set_title(metric)
            ax.set(ylim=(0, None))

            plot_object = io.BytesIO()
            ax.figure.savefig(plot_object, dpi=250.0)
            plot_object.seek(0)
            plot_object.name = '{0}.png'.format(metric)
            plt.close()
            
            send_img_telegram(my_chat_id, plot_object, msg)
        
        else:
            print(f'Алертов нет, спим спокойно.')
    

@dag(default_args=default_args, schedule_interval=schedule_interval, catchup=False)
def alert_report_arakcheev():
    
    # 1 таск. Выгрузка данных из simulator_20230220.feed_actions (fa)
    @task()
    def extract_fa():
        query_fa_metrics = """ 
                            SELECT 
                                toStartOfFifteenMinutes(time) as ts,
                                toDate(time) as date,
                                formatDateTime(ts, '%R') as hm,
                                uniqExact(user_id) as users_feed, 
                                countIf(user_id, action = 'like') likes,
                                countIf(user_id, action = 'view') views,
                                round(likes/views, 3) ctr
                            FROM 
                                simulator_20230220.feed_actions
                            WHERE 
                                time >= today()-1 and time < toStartOfFifteenMinutes(now())
                            GROUP BY
                                ts, date, hm
                            ORDER BY
                                ts
                            format TSVWithNames
                            """
        df_fa_metrics = ch_get_df(query = query_fa_metrics)
        
        return df_fa_metrics
    
    
    # 2 таск. Проверка данных из simulator_20230220.feed_actions (fa) на аномалии
    @task()
    def check_fa(df_fa_metrics):
        fa_metrics = df_fa_metrics.columns.to_list()[3:] # fa_metrics = ['users_feed','likes','views', 'ctr'] 
        run_alert(df_fa_metrics, fa_metrics)
        
    
    # 3 таск. Выгрузка данных из simulator_20230220.message_actions (ma)
    @task()
    def extract_ma():
        query_ma_metrics = """ 
                            SELECT
                                toStartOfFifteenMinutes(time) as ts,
                                toDate(time) as date,
                                formatDateTime(ts,'%R') as hm,
                                uniqExact(user_id) as messager_users, 
                                count(user_id) messages
                            FROM
                                simulator_20230220.message_actions
                            WHERE
                                time >= today()-1 and time < toStartOfFifteenMinutes(now())
                            GROUP BY
                                ts, date, hm
                            ORDER BY
                                ts
                            format TSVWithNames
                            """
        df_ma_metrics = ch_get_df(query = query_ma_metrics)
        
        return df_ma_metrics
    
    
    # 4 таск. Проверка данных из simulator_20230220.message_actions (ma) на аномалии
    @task()
    def check_ma(df_ma_metrics):
        ma_metrics = df_ma_metrics.columns.to_list()[3:] 
        run_alert(df_ma_metrics, ma_metrics)
    
    
    df_fa_metrics = extract_fa()
    check_fa(df_fa_metrics)
    df_ma_metrics = extract_ma()
    check_ma(df_ma_metrics)
    
alert_report_arakcheev = alert_report_arakcheev()