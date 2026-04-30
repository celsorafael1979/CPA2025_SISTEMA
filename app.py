import streamlit as st
import pandas as pd
import pdfplumber
import os
import re
import plotly.express as px
from glob import glob
from io import BytesIO

st.set_page_config(page_title="Sistema CPA 2025 - UEAP", layout="wide")

# Estilo Premium
st.markdown("""
<style>
    .main { background-color: #f8f9fa; }
    .stButton>button { width: 100%; border-radius: 8px; height: 3.5em; background: linear-gradient(45deg, #1e3c72, #2a5298); color: white; font-weight: bold; border: none; }
    .stDownloadButton>button { background: linear-gradient(45deg, #11998e, #38ef7d) !important; color: white !important; border: none; }
</style>
""", unsafe_allow_html=True)

# Inicialização de Estado
if "df_master" not in st.session_state: st.session_state["df_master"] = None

ORDEM_LOGICA = ["Concordo totalmente", "Concordo parcialmente", "Neutro", "Discordo parcialmente", "Discordo totalmente", "Não sei", "Não se aplica"]

def parse_pdf_bytes(file_bytes, filename="PDF"):
    data = []
    try:
        with pdfplumber.open(file_bytes) as pdf:
            segment = "Desconhecido"
            first_text = pdf.pages[0].extract_text()
            if first_text:
                for line in first_text.split('\n'):
                    if "- Segmento:" in line:
                        segment = line.split("Segmento:")[1].strip()
                        break
            cur_dim = "Geral"
            pos = 0
            for page in pdf.pages:
                text = page.extract_text()
                if not text: continue
                lines = text.split('\n')
                for i, line in enumerate(lines):
                    if "Dimensão:" in line: cur_dim = line.split("Dimensão:")[1].strip()
                    m = re.search(r"Pergunta (\d+): (.+)", line)
                    if m:
                        qid, qtxt = m.group(1).strip(), m.group(2).strip()
                        for j in range(i + 1, len(lines)):
                            if "Pergunta" in lines[j] or "Dimensão" in lines[j]:
                                if j > i + 2: break
                            perc_m = re.search(r"(\d+,\d+%)", lines[j])
                            if perc_m:
                                if j + 1 < len(lines):
                                    next_l = lines[j+1].strip()
                                    parts = next_l.split(' ')
                                    if len(parts) >= 2 and parts[-1].isdigit():
                                        data.append({
                                            "Segmento": segment, "Dimensao": cur_dim, "ID": qid,
                                            "Pergunta": qtxt, "Opcao": " ".join(parts[:-1]).strip(),
                                            "Quantidade": int(parts[-1]), "Ordem_Ref": pos
                                        })
                                        pos += 1
    except Exception as e: st.error(f"Erro no arquivo {filename}: {e}")
    return data

def to_excel(df):
    output = BytesIO()
    with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
        df.to_excel(writer, index=False, sheet_name='Resultados')
        workbook = writer.book
        worksheet = writer.sheets['Resultados']
        worksheet.conditional_format(1, 3, len(df), 3, {'type': 'data_bar', 'bar_color': '#63C384'})
    return output.getvalue()

st.sidebar.title("🧭 Painel CPA")
menu = st.sidebar.radio("Navegação:", ["📤 Enviar Arquivos", "📊 Análise de Gráficos"])

if menu == "📤 Enviar Arquivos":
    st.header("📤 Carregamento de Relatórios")
    st.info("Arraste seus arquivos PDF da CPA para começar a análise.")
    
    arquivos_up = st.file_uploader("Selecione os PDFs", type="pdf", accept_multiple_files=True)
    
    if st.button("🚀 Processar e Estruturar"):
        if arquivos_up:
            all_records = []
            progress = st.progress(0)
            for i, f in enumerate(arquivos_up):
                all_records.extend(parse_pdf_bytes(f, f.name))
                progress.progress((i + 1) / len(arquivos_up))
            
            if all_records:
                df = pd.DataFrame(all_records)
                df["Pergunta"] = df["Pergunta"].str.replace(r'\s+', ' ', regex=True).str.strip()
                # Consolidação para evitar duplicatas
                df = df.groupby(["Segmento", "ID", "Pergunta", "Opcao"], as_index=False).agg({"Quantidade": "sum", "Ordem_Ref": "min", "Dimensao": "first"})
                st.session_state["df_master"] = df
                st.success(f"✅ Sucesso! {len(df['Segmento'].unique())} segmentos e {len(df['ID'].unique())} perguntas identificadas.")
            else: st.error("Não foi possível extrair dados dos arquivos.")
        else: st.warning("Por favor, selecione ao menos um arquivo.")

    if st.session_state["df_master"] is not None:
        st.divider()
        st.subheader("📋 Resumo dos Dados Carregados")
        resumo = st.session_state["df_master"].groupby("Segmento")["ID"].nunique().reset_index(name="Qtd Perguntas")
        st.table(resumo)

elif menu == "📊 Análise de Gráficos":
    if st.session_state["df_master"] is None:
        st.warning("⚠️ Nenhum dado carregado. Vá em 'Enviar Arquivos' primeiro.")
    else:
        df = st.session_state["df_master"]
        
        st.sidebar.divider()
        dim = st.sidebar.selectbox("📂 Dimensão:", sorted(df["Dimensao"].unique()))
        df_dim = df[df["Dimensao"] == dim]
        perg = st.sidebar.selectbox("🎯 Pergunta:", sorted(df_dim["Pergunta"].unique()))
        segs_disp = sorted(df[df["Pergunta"] == perg]["Segmento"].unique())
        segs = st.sidebar.multiselect("👥 Segmentos:", segs_disp, default=segs_disp)
        
        tipo = st.sidebar.selectbox("📈 Tipo de Visualização:", ["Barra", "Linha", "Pizza"])
        ordem = st.sidebar.selectbox("↕️ Ordenar por:", ["Original", "Lógica (Pos→Neg)", "Crescente", "Decrescente"])

        if segs:
            df_q = df[df["Pergunta"] == perg].copy()
            ops = df_q[df_q["Segmento"].isin(segs)]["Opcao"].unique()
            template = pd.MultiIndex.from_product([segs, ops], names=["Segmento", "Opcao"]).to_frame(index=False)
            df_plot = pd.merge(template, df_q, on=["Segmento", "Opcao"], how="left").fillna(0)
            
            # Lógica de Ordenação
            if ordem == "Original":
                o_map = df_q.groupby("Opcao")["Ordem_Ref"].min().to_dict()
                df_plot = df_plot.sort_values(["Segmento", "Opcao"], key=lambda x: x.map(o_map) if x.name == "Opcao" else x)
            elif ordem == "Lógica (Pos→Neg)":
                df_plot["Opcao"] = pd.Categorical(df_plot["Opcao"], categories=[o for o in ORDEM_LOGICA if o in ops] + [x for x in ops if x not in ORDEM_LOGICA], ordered=True)
                df_plot = df_plot.sort_values(["Segmento", "Opcao"])
            elif ordem == "Crescente":
                o_val = df_plot.groupby("Opcao")["Quantidade"].mean().sort_values().index
                df_plot["Opcao"] = pd.Categorical(df_plot["Opcao"], categories=o_val, ordered=True)
                df_plot = df_plot.sort_values(["Segmento", "Opcao"])
            elif ordem == "Decrescente":
                o_val = df_plot.groupby("Opcao")["Quantidade"].mean().sort_values(ascending=False).index
                df_plot["Opcao"] = pd.Categorical(df_plot["Opcao"], categories=o_val, ordered=True)
                df_plot = df_plot.sort_values(["Segmento", "Opcao"])

            df_plot["Total"] = df_plot.groupby("Segmento")["Quantidade"].transform("sum")
            df_plot["Percent_Num"] = (df_plot["Quantidade"] / df_plot["Total"] * 100).fillna(0).round(2)
            c_order = df_plot["Opcao"].unique().tolist()
            
            # Gráfico
            titulo = f"<b>{dim}</b><br>{perg}"
            if tipo == "Linha": fig = px.line(df_plot, x="Opcao", y="Percent_Num", color="Segmento", markers=True, category_orders={"Opcao": c_order}, title=titulo)
            elif tipo == "Barra": fig = px.bar(df_plot, x="Opcao", y="Percent_Num", color="Segmento", barmode="group", text="Percent_Num", category_orders={"Opcao": c_order}, title=titulo)
            else: fig = px.pie(df_plot, names="Opcao", values="Quantidade", facet_col="Segmento", facet_col_wrap=2, title=titulo)
            
            fig.update_layout(margin=dict(t=100), yaxis_title="%", xaxis_title="")
            st.plotly_chart(fig, use_container_width=True)
            
            # Exportação
            c1, c2 = st.columns(2)
            with c1:
                st.download_button("📊 Baixar Excel", to_excel(df_plot[["Segmento", "Opcao", "Quantidade", "Percent_Num"]]), "cpa_v2.xlsx")
            with c2:
                st.download_button("🌐 Baixar HTML", fig.to_html(include_plotlyjs='cdn'), "grafico.html")
            
            st.info("💡 **Dica para Imagem HD**: Clique no ícone da **CÂMERA** no canto superior do gráfico para salvar a foto nítida para o Word.")
            st.dataframe(df_plot[["Segmento", "Opcao", "Quantidade", "Percent_Num"]], use_container_width=True)
