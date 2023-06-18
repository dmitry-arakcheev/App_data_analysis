# coding=utf-8

import telegram
import numpy as np
import matplotlib.pyplot as plt
import seaborn as sns
import io
from io import StringIO
import pandas as pd
import pandahouse as ph
import requests
from datetime import datetime, timedelta

from airflow.decorators import dag, task
from airflow.operators.python import get_current_context


# Дефолтные параметры, которые подкидываются в таски
default_args = {
    'owner': 'd-arakcheev',
    'depends_on_past': False,
    'retries': 3,
    'retry_delay': timedelta(minutes=5),
    'start_date': datetime(2023, 3, 23),
}

# Интервал запуска DAG
schedule_interval = '59 10 * * *'

# Настройки телеграм-бота (токен и id чата заменены)
my_token = 'ToKeN:01010' 
my_bot = telegram.Bot(token=my_token) # получаем доступ
my_chat_id = *******


# Функция для clickhouse. Host, user и password заменены.
def ch_get_df(query='Select 1', host='https://*********karpov.courses', user='*****', password='*********'):
    r = requests.post(host, data=query.encode("utf-8"), auth=(user, password), verify=False)
    result = pd.read_csv(StringIO(r.text), sep='\t')
    return result



# Функция для отправки текста в телеграм
def send_mssg_telegram(my_chat_id, mssg):
    my_bot.sendMessage(chat_id=my_chat_id, text=mssg)
    print('Сообщение успешно отправлено')
    
# Функция для фото/изображений в телеграм
def send_img_telegram(my_chat_id, img):
    my_bot.sendPhoto(chat_id=my_chat_id, photo=img)
    print('Изображение успешно отправлено')
    


@dag(default_args=default_args, schedule_interval=schedule_interval, catchup=False)
def dag_daily_feed_report_2(my_chat_id):


    # Первый таск. Выгрузка данных за вчерашний день из simulator_20230220.feed_actions (fa)
    @task()
    def extract_fa_yesterday():
        query_yestrd_metrics = """SELECT 
                                      yesterday() AS date,
                                      uniq(user_id) AS DAU,
                                      countIf(action, action = 'view') AS views,
                                      countIf(action, action = 'like') AS likes,
                                      ROUND(countIf(action, action = 'like') / countIf(action, action = 'view'), 2) AS ctr
                                    FROM
                                      simulator_20230220.feed_actions
                                    WHERE
                                      toDate(time) = yesterday()
                                    format TSVWithNames
                                    """
        df_fa_yesterday = ch_get_df(query = query_yestrd_metrics)
        return df_fa_yesterday
    
    # Второй таск. Выгрузка данных за последние 7 дней из simulator_20230220.feed_actions (fa)
    @task()
    def extract_fa_7days_metrics():
        query_7days_metrics = """ SELECT 
                                      time::DATE AS date,
                                      uniq(user_id) AS DAU,
                                      countIf(action, action = 'view') AS views,
                                      countIf(action, action = 'like') AS likes,
                                      ROUND(countIf(action, action = 'like') / countIf(action, action = 'view'), 2) AS ctr
                                    FROM
                                      simulator_20230220.feed_actions
                                    WHERE
                                      toDate(time) BETWEEN (today()-7) AND yesterday()
                                    GROUP BY 
                                      date
                                    ORDER BY
                                      date
                                    format TSVWithNames
                                    """
        df_7days_metrics = ch_get_df(query = query_7days_metrics)
        return df_7days_metrics

    # Третий таск. Формирование текстового отчета за вчерашний день
    @task()
    def transform_fa_yesterday(df_fa_yesterday):
        dict_yestrd_metrics = df_fa_yesterday.to_dict(orient='list')
        date = dict_yestrd_metrics['date'][0]
        DAU = dict_yestrd_metrics['DAU'][0]
        views = dict_yestrd_metrics['views'][0]
        likes = dict_yestrd_metrics['likes'][0]
        ctr = dict_yestrd_metrics['ctr'][0]
        
        mssg_yestrd_metrics = f'Отчет по ключевым метрикам за {date}:\n DAU - {DAU};\n views - {views};\n likes - {likes};\n ctr - {ctr}.'
        
        return mssg_yestrd_metrics
    
    
    # Четвертый таск. Формирование и отправка графического отчета за последние 7 дней
    @task()
    def transform_and_send_fa_7days_metrics(my_chat_id, df_7days_metrics):
        
        mssg_7days_metrics = f'Графический отчет по ключевым метрикам за последние 7 дней.'
        send_mssg_telegram(my_chat_id, mssg_7days_metrics)
        
        metrics = df_7days_metrics.columns.values[1:].tolist()
                
        sns.set(rc={'figure.figsize':(15,7)})
        for metric in metrics:
            sns.lineplot(data = df_7days_metrics, x = "date", y = metric)
            plt.title(f'{metric} plot')
            plot_object = io.BytesIO()
            plt.savefig(plot_object, dpi='figure')
            plot_object.seek(0)
            plot_object.name = f'{metric} last 7 days.png'
            plt.close()
            my_bot.sendPhoto(chat_id=my_chat_id, photo=plot_object)
        
           
    
    # Пятый  таск. Отправка текстового отчета за вчерашний день
    @task()
    def send_fa_yesterday(my_chat_id, mssg_yestrd_metrics):
        send_mssg_telegram(my_chat_id, mssg_yestrd_metrics)
    
        
    df_fa_yesterday = extract_fa_yesterday()
    df_7days_metrics = extract_fa_7days_metrics()
    mssg_yestrd_metrics = transform_fa_yesterday(df_fa_yesterday)
    transform_and_send_fa_7days_metrics(my_chat_id, df_7days_metrics)
    send_fa_yesterday(my_chat_id, mssg_yestrd_metrics)

    
dag_daily_feed_report_2 = dag_daily_feed_report_2(my_chat_id)