# coding=utf-8

from datetime import datetime, timedelta
import pandas as pd
import pandahouse as ph
from io import StringIO
import requests

from airflow.decorators import dag, task
from airflow.operators.python import get_current_context


# Функция для clickhouse. Host, user и password заменены.
def ch_get_df(query='Select 1', host='https://**********karpov.courses', user='*******', password='*******'):
    r = requests.post(host, data=query.encode("utf-8"), auth=(user, password), verify=False)
    result = pd.read_csv(StringIO(r.text), sep='\t')
    return result


query = """SELECT 
               toDate(time) as event_date, 
               country, 
               source,
               count() as likes
            FROM 
                simulator.feed_actions 
            where 
                toDate(time) = '2022-01-26' 
                and action = 'like'
            group by
                event_date,
                country,
                source
            format TSVWithNames"""

# Дефолтные параметры, которые прокидываются в таски
default_args = {
    'owner': 'd-arakcheev',
    'depends_on_past': False,
    'retries': 3,
    'retry_delay': timedelta(minutes=10),
    'start_date': datetime(2023, 3, 15),
}

# Интервал запуска DAG
schedule_interval = '0 22 * * *'

def upload_to_test(df):
    connection_to_upload = {
        'host': 'https://************karpov.courses',
        'password': '**********',
        'user': '*********',
        'database': 'test'
    }
    
    query_to_upload = '''CREATE TABLE IF NOT EXISTS test.d_arakcheev_lesson_6
                            (event_date Date,
                            dimension String,
                            dimension_value String,
                            views Int64,
                            likes Int64,
                            messages_received Int64,
                            messages_sent Int64,
                            users_received Int64,
                            users_sent Int64) 
                            ENGINE = MergeTree()
                            ORDER BY event_date'''
    ph.execute(connection = connection_to_upload, query = query_to_upload)
    ph.to_clickhouse(df, 'd_arakcheev_lesson_6', connection = connection_to_upload, index=False)




@dag(default_args=default_args, schedule_interval=schedule_interval, catchup=False)
def dag_sim_an():


    # Первый таск. Выгрузка данных из simulator_20230220.feed_actions (fa)
    @task()
    def extract_fa():
        query = """SELECT
                        toDate(time) AS event_date,
                        user_id,
                        age,
                        gender,
                        os,
                        countIf(action='like') AS likes,
                        countIf(action='view') AS views
                    FROM
                        simulator_20230220.feed_actions
                    WHERE
                        toDate(time) = today()-1
                    GROUP BY
                        event_date,
                        user_id,
                        age,
                        gender,
                        os
                    format TSVWithNames"""
        df_fa = ch_get_df(query=query)
        return df_fa

    # Второй таск. Выгрузка данных из simulator_20230220.message_actions (ma)
    @task()
    def extract_ma():
        query = """WITH ma_users_yesterday AS (SELECT
                                                    toDate(time) AS event_date,
                                                    user_id,
                                                    age,
                                                    gender,
                                                    os,
                                                    COUNT(reciever_id) AS messages_sent,
                                                    uniq(reciever_id) AS users_sent
                                                FROM
                                                    simulator_20230220.message_actions
                                                WHERE
                                                    toDate(time) = today()-1
                                                GROUP BY
                                                    event_date,
                                                    user_id,
                                                    age,
                                                    gender,
                                                    os),
                    ma_recievers_yesterday AS (SELECT
                                                    toDate(time) AS event_date,
                                                    reciever_id,
                                                    COUNT() AS messages_received,
                                                    uniq(user_id) AS users_received
                                                FROM
                                                    simulator_20230220.message_actions
                                                WHERE
                                                    toDate(time) = today()-1
                                                GROUP BY
                                                    event_date,
                                                reciever_id)

                    SELECT
                        event_date,
                        user_id,
                        age,
                        gender,
                        os,
                        messages_sent,
                        users_sent,
                        messages_received,
                        users_received
                    FROM
                        ma_users_yesterday AS muy
                        FULL OUTER JOIN ma_recievers_yesterday AS mry ON muy.user_id = mry.reciever_id
                    WHERE
                        event_date = today()-1
                    ORDER BY
                        user_id
                    format TSVWithNames"""
        df_ma = ch_get_df(query=query)
        return df_ma

    # объединяем выгруженные таблицы в одну
    @task
    def merge_fa_ma(df_fa, df_ma):
        merged_fa_ma = df_fa.merge(df_ma, how='outer', on=['event_date', 'user_id', 'age', 'gender', 'os'])
        return merged_fa_ma
    
    # считаем метрики в разрезе по полу
    @task
    def get_dimension_gender(merged_fa_ma):
        metrics_dimension_gender = merged_fa_ma[
            ['event_date', 'gender', 'likes', 'views', 'messages_sent', 'messages_received', 'users_sent', 'users_received']] \
            .groupby(['event_date', 'gender'], as_index=False).sum().rename(columns={'gender': 'dimension_value'})
        metrics_dimension_gender['dimension'] = 'gender'
        return metrics_dimension_gender
    
    
    
    # считаем метрики в разрезе по возрасту
    @task
    def get_dimension_age(merged_fa_ma):
        metrics_dimension_age = merged_fa_ma[
            ['event_date', 'age', 'likes', 'views', 'messages_sent', 'messages_received', 'users_sent', 'users_received']] \
            .groupby(['event_date', 'age'], as_index=False).sum().rename(columns={'age': 'dimension_value'})
        metrics_dimension_age['dimension'] = 'age'
        return metrics_dimension_age
    
    
    # считаем метрики в разрезе по ос
    @task
    def get_dimension_os(merged_fa_ma):
        metrics_dimension_os = merged_fa_ma[
            ['event_date', 'os', 'likes', 'views', 'messages_sent', 'messages_received', 'users_sent', 'users_received']] \
            .groupby(['event_date', 'os'], as_index=False).sum().rename(columns={'os': 'dimension_value'})
        metrics_dimension_os['dimension'] = 'os'
        return metrics_dimension_os
    
    
    # соединяем таблицы и загружаем
    @task
    def concat_and_upload(metrics_dimension_gender, metrics_dimension_age, metrics_dimension_os):
        # соединяем таблицы
        all_dimentions = pd.concat([metrics_dimension_gender, metrics_dimension_age, metrics_dimension_os], ignore_index=True)
        all_dimentions = all_dimentions[['event_date','dimension','dimension_value', 'views', 'likes', 'messages_received', 'messages_sent' ,'users_received' ,'users_sent']]
        all_dimentions = all_dimentions.astype({"event_date":"datetime64","likes":"int","views":"int", "messages_received":"int","messages_sent":"int", "users_sent":"int","users_received":"int"})
        
        # загружаем
        print('uploading table...')
        upload_to_test(all_dimentions)
        print('Table successfully uploaded. Congrats')
    
    
    
    
    extract_fa = extract_fa()
    extract_ma = extract_ma()
    merged_fa_ma = merge_fa_ma(extract_fa, extract_ma)
    metrics_dimension_gender = get_dimension_gender(merged_fa_ma)
    metrics_dimension_age = get_dimension_age(merged_fa_ma)
    metrics_dimension_os = get_dimension_os(merged_fa_ma)
    concat_and_upload = concat_and_upload(metrics_dimension_gender, metrics_dimension_age, metrics_dimension_os)
    
    
dag_sim_an = dag_sim_an()    
    
