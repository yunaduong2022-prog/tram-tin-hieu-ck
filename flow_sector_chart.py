"""Shared market flow presentation. Coverage is the intersection with the EOD universe."""
from pathlib import Path
import pandas as pd
import plotly.express as px

def sector_figure(ranked, value_col, membership, eod_path='data/eod_prices.csv'):
    universe=pd.read_csv(eod_path,usecols=['Mã'],dtype=str,encoding='utf-8-sig')['Mã'].dropna().str.strip().str.upper().drop_duplicates()
    expected=universe.map(membership).fillna('Khác').value_counts()
    r=ranked[['symbol','Nhóm ngành',value_col]].copy()
    r['symbol']=r.symbol.astype(str).str.strip().str.upper()
    r['known_symbol']=r.symbol.where(r.symbol.isin(universe))
    g=r.groupby('Nhóm ngành',dropna=False).agg(value=(value_col,'sum'),observed=('symbol','nunique'),known_observed=('known_symbol','nunique')).reset_index().sort_values('value')
    g['expected']=g['Nhóm ngành'].map(expected).fillna(0).astype(int)
    def label(r):
        outside=int(r.observed-r.known_observed)
        suffix=f' + {outside} ngoài kho' if outside else ''
        return f"{r['Nhóm ngành']} · {int(r.known_observed)}/{int(r.expected)} mã{suffix}"
    g['label']=g.apply(label,axis=1)
    g['direction']=g.value.map(lambda x:'Mua ròng' if x>0 else ('Bán ròng' if x<0 else 'Cân bằng'))
    fig=px.bar(g,y='label',x='value',orientation='h',text=g.value.map(lambda x:f'{x:+,.2f}'),color='direction',color_discrete_map={'Mua ròng':'#229970','Bán ròng':'#dd5660','Cân bằng':'#87958f'},labels={'value':'Tỷ đồng','label':'Nhóm ngành'},hover_data={'observed':True,'expected':True,'known_observed':True,'direction':False})
    fig.update_traces(textposition='outside',cliponaxis=False)
    fig.update_yaxes(categoryorder='array',categoryarray=g.label.tolist(),tickmode='linear',dtick=1,automargin=True)
    fig.update_layout(height=max(430,len(g)*32+90),showlegend=False,margin=dict(l=10,r=100,t=20,b=35))
    return fig
