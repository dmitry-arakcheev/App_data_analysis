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
def app_report_arakcheev(my_chat_id):

    # Первый таск. Выгрузка данных за последние 7 дней из simulator_20230220.feed_actions (fa)
    @task()
    def extract_fa_7days():
        query_fa_7days_metrics = """ SELECT 
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
        df_fa_7days_metrics = ch_get_df(query = query_fa_7days_metrics)
        return df_fa_7days_metrics
    
    # Второй таск. Формирование графического отчета ленты новостей за последние 7 дней
    @task()
    def transform_fa_7days_metrics(df_fa_7days_metrics):
        
        DAU_top = round(df_fa_7days_metrics.DAU.max()*1.2, -3)
        ctr_top = round(df_fa_7days_metrics.ctr.max()*1.5, 1)
        views_top = round(df_fa_7days_metrics.views.max()*1.1, -3)
        likes_top = round(df_fa_7days_metrics.likes.max()*1.1, -3)
        
        fig_fa_7days, ((ax1, ax2), (ax3, ax4)) = plt.subplots(2, 2, figsize=(20, 15))

        fig_fa_7days.suptitle('Динамика показателей ленты новостей за последние 7 дней', fontsize=25)

        sns.lineplot(ax = ax1, data = df_fa_7days_metrics, x = 'date', y = 'DAU')
        ax1.set_title('DAU')
        ax1.set_ylim([0, DAU_top])
        ax1.grid()

        sns.lineplot(ax = ax2, data = df_fa_7days_metrics, x = 'date', y = 'ctr')
        ax2.set_title('ctr')
        ax2.set_ylim([0, ctr_top])
        ax2.grid()

        sns.lineplot(ax = ax3, data = df_fa_7days_metrics, x = 'date', y = 'views')
        ax3.set_title('Просмотры')
        ax3.set_ylim([0, views_top])
        ax3.grid()

        sns.lineplot(ax = ax4, data = df_fa_7days_metrics, x = 'date', y = 'likes')
        ax4.set_title('Лайки')
        ax4.set_ylim([0, likes_top])
        ax4.grid()
        
        fig_fa_7days_object = io.BytesIO()
        fig_fa_7days.savefig(fig_fa_7days_object, dpi=250.0)
        fig_fa_7days_object.seek(0)
        fig_fa_7days_object.name = 'Feed actions metrics per last 7 days.png'
        plt.close()
        
        return fig_fa_7days_object
    
    # Третий  таск. Отправка графического отчета ленты новостей за последние 7 дней
    @task()
    def send_fa_7days_metrics(my_chat_id, fig_fa_7days_object):
        send_img_telegram(my_chat_id, fig_fa_7days_object)
        print('Графический отчет по ленте новостей за последние 7 дней успешно отправлен')
   

    # Четвертый таск. Выгрузка данных за последние 7 дней из simulator_20230220.message_actions (ma)
    @task()
    def extract_ma_7days():
        query_ma_7days_metrics = """ SELECT 
                                        uniq(user_id) AS uniq_users,
                                        toDate(time) AS date,
                                        COUNT(reciever_id) AS total_messages,
                                        ROUND(total_messages / uniq_users, 2) AS mssgs_per_user
                                    FROM
                                        simulator_20230220.message_actions
                                    WHERE
                                        toDate(time) BETWEEN (today()-7) AND yesterday()
                                    GROUP BY 
                                        date
                                    ORDER BY
                                        date
                                    format TSVWithNames
                                    """
        df_ma_7days_metrics = ch_get_df(query = query_ma_7days_metrics)
        return df_ma_7days_metrics
    
    
    # Пятый таск. Формирование графического отчета мессенджера за последние 7 дней
    @task()
    def transform_ma_7days_metrics(df_ma_7days_metrics):
        
        uniq_users_top = round(df_ma_7days_metrics.uniq_users.max()*1.4, -3)
        total_messages_top = round(df_ma_7days_metrics.total_messages.max()*1.2, -3)
        mssgs_per_user_top = round(df_ma_7days_metrics.mssgs_per_user.max()*1.2, -1)
        
        fig_ma_7days, (ax1, ax2, ax3) = plt.subplots(3, figsize=(20, 20))

        fig_ma_7days.suptitle('Динамика показателей мессенджера за последние 7 дней', fontsize=25)

        sns.lineplot(ax = ax1, data = df_ma_7days_metrics, x = 'date', y = 'uniq_users')
        ax1.set_title('Уникальные пользователи')
        ax1.set_ylim([0, uniq_users_top])
        ax1.grid()

        sns.lineplot(ax = ax2, data = df_ma_7days_metrics, x = 'date', y = 'total_messages')
        ax2.set_title('Всего сообщений')
        ax2.set_ylim([0, total_messages_top])
        ax2.grid()

        sns.lineplot(ax = ax3, data = df_ma_7days_metrics, x = 'date', y = 'mssgs_per_user')
        ax3.set_title('Сообщений на 1 пользователя')
        ax3.set_ylim([0, mssgs_per_user_top])
        ax3.grid()
        
        fig_ma_7days_object = io.BytesIO()
        fig_ma_7days.savefig(fig_ma_7days_object, dpi=250.0)
        fig_ma_7days_object.seek(0)
        fig_ma_7days_object.name = 'Message actions metrics per last 7 days.png'
        plt.close()
        
        return fig_ma_7days_object
    
    
    # Шестой  таск. Отправка графического отчета по мессенджеру за последние 7 дней
    @task()
    def send_ma_7days_metrics(my_chat_id, fig_ma_7days_object):
        send_img_telegram(my_chat_id, fig_ma_7days_object)
        print('Графический отчет по мессенджеру за последние 7 дней успешно отправлен')
        
        
    # Седьмой таск. Выгрузка данных за последние 7 дней по новым пользователям из simulator_20230220.feed_actions (fa)
    # Чтобы не перегружать запрос не беру в расчет message_actions, так как уникальных пользователей только мессенджера единицы.
    @task()
    def extract_newcomers():
        query_newcomers = """ WITH sq1 AS (SELECT
                                                DISTINCT user_id AS user_id,
                                                time::DATE AS date,
                                                MIN(time::DATE) OVER (PARTITION BY user_id ORDER BY time::DATE) AS first_day
                                              FROM
                                                simulator_20230220.feed_actions),
                              sq2 AS (SELECT
                                          user_id,
                                          date,
                                          first_day,
                                          IF(date = first_day, 'newcomer', '-') AS user_status
                                        FROM
                                          sq1)

                            SELECT
                              date,
                              uniq(user_id) AS newcomers
                            FROM
                              sq2
                            WHERE 
                              user_status = 'newcomer'
                              AND date BETWEEN (today()-7) AND yesterday()
                            GROUP BY
                              date
                            format TSVWithNames
                                    """
        df_newcomers = ch_get_df(query = query_newcomers)
        return df_newcomers
    
    # Восьмой таск. Формирование графического отчета по новым пользователям за последние 7 дней
    @task()
    def transform_newcomers(df_newcomers):
        
        newcomers_top = round(df_newcomers.newcomers.max()*1.6, -2)
        
        fig_newcomers, ax1 = plt.subplots(1, figsize=(20, 10))

        fig_newcomers.suptitle('Динамика прихода новых пользователей за последние 7 дней', fontsize=25)

        sns.lineplot(ax = ax1, data = df_newcomers, x = 'date', y = 'newcomers')
        ax1.set_title('Новые пользователи')
        ax1.set_ylim([0, newcomers_top])
        ax1.grid()
        
        newcomers_plot_object = io.BytesIO()
        fig_newcomers.savefig(newcomers_plot_object, dpi=250.0)
        newcomers_plot_object.seek(0)
        newcomers_plot_object.name = 'newcomers per last 7 days.png'
        plt.close()
        
        return newcomers_plot_object
    
    # Девятый  таск. Отправка графического отчета по новым пользователям за последние 7 дней
    @task()
    def send_newcomers(my_chat_id, newcomers_plot_object):
        send_img_telegram(my_chat_id, newcomers_plot_object)
        print('Графический отчет по новым пользователям за последние 7 дней успешно отправлен')
        
    
    # Десятый таск. Выгрузка данных за последние 7 дней из simulator_20230220.feed_actions (fa) и simulator_20230220.message_actions (ma) в разрезе os
    @task()
    def extract_7days_os():
        query_7days_os = """ WITH sq1 AS (SELECT 
                                                DISTINCT user_id AS users,
                                                toDate(time) AS date,
                                                os
                                              FROM
                                                simulator_20230220.message_actions
                                              WHERE
                                                toDate(time) BETWEEN (today()-7) AND yesterday()),
                                sq2 AS (SELECT
                                            DISTINCT user_id AS users,
                                            toDate(time) AS date,
                                            os
                                        FROM
                                            simulator_20230220.feed_actions
                                        WHERE
                                            toDate(time) BETWEEN (today()-7) AND yesterday())
                                SELECT
                                    date,
                                    uniq(users) AS uniq_users,
                                    os
                                FROM
                                    sq1
                                    FULL JOIN sq2 using(date, users, os)
                                GROUP BY
                                    date,
                                    os
                                    format TSVWithNames
                                    """
        df_7days_os = ch_get_df(query = query_7days_os)
        return df_7days_os
    
    # Одиннадцатый таск. Формирование графического отчета за последние 7 дней в разрезе os
    @task()
    def transform_7days_os(df_7days_os):
        
        uniq_users_top = round(df_7days_os.uniq_users.max()*1.4, -3)
        
        fig_7days_os, ax1 = plt.subplots(1, figsize=(20, 10))

        fig_7days_os.suptitle('Количествой пользователей за последние 7 дней в разрезе OS', fontsize=25)

        sns.barplot(ax = ax1, data = df_7days_os, x = 'date', y = 'uniq_users', hue='os')
        ax1.set_title('Пользователи по OS')
        ax1.set_ylim([0, uniq_users_top])
        ax1.grid()
        
        os_plot_object = io.BytesIO()
        fig_7days_os.savefig(os_plot_object, dpi=250.0)
        os_plot_object.seek(0)
        os_plot_object.name = 'users per os last 7 days.png'
        plt.close()
        
        return os_plot_object
    
    
    # Двенадцатый таск. Отправка графического отчета за последние 7 дней в разрезе os
    @task()
    def send_7days_os(my_chat_id, os_plot_object):
        send_img_telegram(my_chat_id, os_plot_object)
        print('Графический отчет по пользователям за последние 7 дней в разрезе os успешно отправлен')
        
       
    # 13 таск. Выгрузка данных за последние 7 дней из simulator_20230220.feed_actions (fa) и simulator_20230220.message_actions (ma) в разрезе источника привлечения трафика
    @task()
    def extract_7days_source():
        query_7days_source = """ WITH sq1 AS (SELECT 
                                                DISTINCT user_id AS users,
                                                toDate(time) AS date,
                                                source
                                              FROM
                                                simulator_20230220.message_actions
                                              WHERE
                                                toDate(time) BETWEEN (today()-7) AND yesterday()),
                                sq2 AS (SELECT
                                            DISTINCT user_id AS users,
                                            toDate(time) AS date,
                                            source
                                        FROM
                                            simulator_20230220.feed_actions
                                        WHERE
                                            toDate(time) BETWEEN (today()-7) AND yesterday())
                                SELECT
                                    date,
                                    uniq(users) AS uniq_users,
                                    source
                                FROM
                                    sq1
                                    FULL JOIN sq2 using(date, users, source)
                                GROUP BY
                                    date,
                                    source
                                    format TSVWithNames
                                    """
        df_7days_source = ch_get_df(query = query_7days_source)
        return df_7days_source
    
    # 14 таск. Формирование графического отчета за последние 7 дней в разрезе source
    @task()
    def transform_7days_source(df_7days_source):
        
        uniq_users_top = round(df_7days_source.uniq_users.max()*1.4, -3)
        
        fig_7days_source, ax2 = plt.subplots(1, figsize=(20, 10))

        fig_7days_source.suptitle('Количествой пользователей за последние 7 дней в разрезе source', fontsize=25)

        sns.barplot(ax = ax2, data = df_7days_source, x = 'date', y = 'uniq_users', hue='source')
        ax2.set_title('Пользователи по source')
        ax2.set_ylim([0, uniq_users_top])
        ax2.grid()
        
        source_plot_object = io.BytesIO()
        fig_7days_source.savefig(source_plot_object, dpi=250.0)
        source_plot_object.seek(0)
        source_plot_object.name = 'users per source last 7 days.png'
        plt.close()
        
        return source_plot_object
    
    
    # 15 таск. Отправка графического отчета за последние 7 дней в разрезе source
    @task()
    def send_7days_source(my_chat_id, source_plot_object):
        send_img_telegram(my_chat_id, source_plot_object)
        print('Графический отчет по пользователям за последние 7 дней в разрезе source успешно отправлен')
        

    df_fa_7days_metrics = extract_fa_7days()
    fig_fa_7days_object = transform_fa_7days_metrics(df_fa_7days_metrics)
    send_fa_7days_metrics(my_chat_id, fig_fa_7days_object)

    df_ma_7days_metrics = extract_ma_7days()
    fig_ma_7days_object = transform_ma_7days_metrics(df_ma_7days_metrics)
    send_ma_7days_metrics(my_chat_id, fig_ma_7days_object)

    df_newcomers = extract_newcomers()
    newcomers_plot_object = transform_newcomers(df_newcomers)
    send_newcomers(my_chat_id, newcomers_plot_object)

    df_7days_os = extract_7days_os()
    os_plot_object = transform_7days_os(df_7days_os)
    send_7days_os(my_chat_id, os_plot_object)

    df_7days_source = extract_7days_source()
    source_plot_object = transform_7days_source(df_7days_source)
    send_7days_source(my_chat_id, source_plot_object)
    
app_report_arakcheev = app_report_arakcheev(my_chat_id)