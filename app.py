import streamlit as st
import pandas as pd
import pdfplumber
import os
import re
import plotly.express as px
from glob import glob
from io import BytesIO
from supabase import create_client, Client

st.set_page_config(page_title="Sistema CPA 2025 - UEAP", layout="wide")

# Estilo Premium
st.markdown("""
<style>
    .main { background-color: #f8f9fa; }
    .stButton>button { width: 100%; border-radius: 8px; height: 3.5em; background: linear-gradient(45deg, #1e3c72, #2a5298); color: white; font-weight: bold; border: none; }
    .stDownloadButton>button { background: linear-gradient(45deg, #11998e, #38ef7d) !important; color: white !important; border: none; }
</style>
""", unsafe_allow_html=True)

# Conexão e Funções do Supabase
@st.cache_resource
def get_supabase_client() -> Client:
    if "supabase" in st.secrets:
        url = st.secrets["supabase"].get("url")
        key = st.secrets["supabase"].get("key")
        if url and key:
            try:
                return create_client(url, key)
            except Exception as e:
                st.error(f"Erro ao conectar ao Supabase: {e}")
    return None

def load_data_from_supabase(client: Client):
    try:
        all_data = []
        limit = 1000
        offset = 0
        while True:
            response = client.table("cpa_dados").select("*").range(offset, offset + limit - 1).execute()
            if not response.data:
                break
            all_data.extend(response.data)
            if len(response.data) < limit:
                break
            offset += limit
        
        if not all_data:
            return None
        
        df = pd.DataFrame(all_data)
        df = df.rename(columns={
            "campus": "Campus",
            "segmento": "Segmento",
            "dimensao": "Dimensao",
            "id_pergunta": "ID",
            "pergunta": "Pergunta",
            "opcao": "Opcao",
            "quantidade": "Quantidade",
            "ordem_ref": "Ordem_Ref"
        })
        df["Quantidade"] = df["Quantidade"].astype(int)
        df["Ordem_Ref"] = df["Ordem_Ref"].astype(int)
        df = df.sort_values(by=["Campus", "Segmento", "ID", "Ordem_Ref"])
        return df
    except Exception as e:
        st.error(f"Erro ao carregar dados do Supabase: {e}")
        return None

def delete_all_data_from_supabase(client: Client):
    try:
        client.table("cpa_dados").delete().neq("id", 0).execute()
        return True
    except Exception as e:
        st.error(f"Erro ao limpar dados do Supabase: {e}")
        return False

def save_data_to_supabase(client: Client, df: pd.DataFrame):
    try:
        records = []
        for _, row in df.iterrows():
            records.append({
                "campus": row["Campus"],
                "segmento": row["Segmento"],
                "dimensao": row["Dimensao"],
                "id_pergunta": str(row["ID"]),
                "pergunta": row["Pergunta"],
                "opcao": row["Opcao"],
                "quantidade": int(row["Quantidade"]),
                "ordem_ref": int(row["Ordem_Ref"])
            })
        
        batch_size = 1000
        for i in range(0, len(records), batch_size):
            batch = records[i:i+batch_size]
            client.table("cpa_dados").upsert(batch, on_conflict="campus,segmento,id_pergunta,opcao").execute()
        return True
    except Exception as e:
        st.error(f"Erro ao salvar dados no Supabase: {e}")
        return False


# Inicialização de Estado
if "df_master" not in st.session_state:
    st.session_state["df_master"] = None

supabase_client = get_supabase_client()

# Carrega do banco automaticamente no primeiro acesso
if st.session_state["df_master"] is None and supabase_client:
    st.session_state["df_master"] = load_data_from_supabase(supabase_client)

ORDEM_LOGICA = ["Concordo totalmente", "Concordo parcialmente", "Neutro", "Discordo parcialmente", "Discordo totalmente", "Não sei", "Não se aplica"]
SENTIMENT_MAP = {
    "Concordo totalmente": "Positiva",
    "Concordo parcialmente": "Positiva",
    "Neutro": "Neutro",
    "Discordo parcialmente": "Negativa",
    "Discordo totalmente": "Negativa"
}
SENTIMENT_COLORS = {"Positiva": "#2ecc71", "Neutro": "#f1c40f", "Negativa": "#e74c3c"}

def parse_pdf_bytes(file_bytes, filename="PDF"):
    data = []
    try:
        with pdfplumber.open(file_bytes) as pdf:
            segment = "Desconhecido"
            campus = "Desconhecido"
            first_text = pdf.pages[0].extract_text()
            if first_text:
                for line in first_text.split('\n'):
                    if "- Segmento:" in line:
                        segment = line.split("Segmento:")[1].strip()
                    if "- Campus:" in line:
                        campus = line.split("Campus:")[1].strip()
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
                                            "Campus": campus, "Segmento": segment, "Dimensao": cur_dim, "ID": qid,
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
if supabase_client:
    st.sidebar.markdown(
        '<div style="background-color: #d4edda; color: #155724; padding: 10px; border-radius: 5px; margin-bottom: 20px; font-weight: bold; text-align: center; border: 1px solid #c3e6cb;">⚡ Supabase Conectado</div>',
        unsafe_allow_html=True
    )
else:
    st.sidebar.markdown(
        '<div style="background-color: #fff3cd; color: #856404; padding: 10px; border-radius: 5px; margin-bottom: 20px; font-weight: bold; text-align: center; border: 1px solid #ffeeba;">⚠️ Modo Local (Sem Banco)</div>',
        unsafe_allow_html=True
    )
menu = st.sidebar.radio("Navegação:", ["📤 Enviar Arquivos", "📊 Análise de Gráficos"], index=1)

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
                df = df.groupby(["Campus", "Segmento", "ID", "Pergunta", "Opcao"], as_index=False).agg({"Quantidade": "sum", "Ordem_Ref": "min", "Dimensao": "first"})
                
                if supabase_client:
                    with st.spinner("Limpando dados antigos e salvando no Supabase..."):
                        if delete_all_data_from_supabase(supabase_client):
                            if save_data_to_supabase(supabase_client, df):
                                st.success("✅ Dados salvos com sucesso no banco de dados!")
                                st.session_state["df_master"] = load_data_from_supabase(supabase_client)
                            else:
                                st.warning("⚠️ Ocorreu um erro ao salvar os novos dados no Supabase. Os dados foram carregados apenas temporariamente.")
                                st.session_state["df_master"] = df
                        else:
                            st.warning("⚠️ Não foi possível limpar os dados antigos no Supabase. A operação de salvamento foi cancelada para evitar duplicidade.")
                            st.session_state["df_master"] = df
                else:
                    st.session_state["df_master"] = df
                    st.success("✅ Dados processados localmente com sucesso.")
            else: st.error("Não foi possível extrair dados dos arquivos.")
        else: st.warning("Por favor, selecione ao menos um arquivo.")

    if st.session_state["df_master"] is not None:
        st.divider()
        st.subheader("📋 Resumo dos Dados Carregados")
        resumo = st.session_state["df_master"].groupby(["Campus", "Segmento"])["ID"].nunique().reset_index(name="Qtd Perguntas")
        st.table(resumo)
        
        if supabase_client:
            st.divider()
            st.subheader("⚙️ Gerenciamento de Banco de Dados")
            col_db1, col_db2 = st.columns(2)
            with col_db1:
                if st.button("🔄 Sincronizar com o Banco"):
                    with st.spinner("Sincronizando..."):
                        df_db = load_data_from_supabase(supabase_client)
                        if df_db is not None:
                            st.session_state["df_master"] = df_db
                            st.success("✅ Dados sincronizados do banco com sucesso!")
                            st.rerun()
                        else:
                            st.info("ℹ️ O banco de dados está vazio.")
            with col_db2:
                confirmar_limpar = st.checkbox("Confirmar exclusão permanente dos dados do banco", value=False)
                if st.button("🗑️ Limpar Banco de Dados", disabled=not confirmar_limpar, type="primary"):
                    with st.spinner("Excluindo dados..."):
                        try:
                            supabase_client.table("cpa_dados").delete().neq("id", 0).execute()
                            st.session_state["df_master"] = None
                            st.success("🗑️ Todos os dados do banco foram excluídos!")
                            st.rerun()
                        except Exception as e:
                            st.error(f"Erro ao excluir dados: {e}")

elif menu == "📊 Análise de Gráficos":
    if st.session_state["df_master"] is None:
        st.warning("⚠️ Nenhum dado carregado. Vá em 'Enviar Arquivos' primeiro.")
    else:
        df = st.session_state["df_master"]

        st.sidebar.divider()
        dim = st.sidebar.selectbox("📂 Dimensão:", sorted(df["Dimensao"].unique()))
        df_dim = df[df["Dimensao"] == dim]
        perg = st.sidebar.selectbox("🎯 Pergunta:", sorted(df_dim["Pergunta"].unique()))

        campus_disp = sorted(df[df["Pergunta"] == perg]["Campus"].unique())
        campus_selecionados = st.sidebar.multiselect("🏛️ Campus:", campus_disp, default=campus_disp)

        df_campus = df[df["Campus"].isin(campus_selecionados)] if campus_selecionados else df.iloc[:0]
        segs_disp = sorted(df_campus[df_campus["Pergunta"] == perg]["Segmento"].unique())
        segs = st.sidebar.multiselect("👥 Segmentos:", segs_disp, default=segs_disp)

        opcoes_disp = sorted(df_campus[df_campus["Pergunta"] == perg]["Opcao"].unique(), key=lambda x: ORDEM_LOGICA.index(x) if x in ORDEM_LOGICA else 99)
        opcoes_selecionadas = st.sidebar.multiselect("📝 Opções de Resposta:", opcoes_disp, default=opcoes_disp)

        tipo = st.sidebar.selectbox("📈 Tipo de Visualização:", ["Barra", "Linha", "Pizza"])
        ordem = st.sidebar.selectbox("↕️ Ordenar por:", ["Original", "Lógica (Pos→Neg)", "Crescente", "Decrescente"])

        st.sidebar.divider()
        st.sidebar.subheader("⚙️ Opções de Visualização")
        formato_valor = st.sidebar.radio("Mostrar Valores Como:", ["Porcentagem", "Absoluto"])
        campo_calculado = st.sidebar.checkbox("Mostrar apenas Média dos Segmentos", value=False)
        agrupar_sentimento = st.sidebar.checkbox("Agrupar por Sentimento (Pos/Neu/Neg)", value=False)

        st.sidebar.divider()
        st.sidebar.subheader("🎨 Configurações de Tamanho")
        c_width = st.sidebar.slider("Largura (px)", 400, 1400, 1000)
        c_height = st.sidebar.slider("Altura (px)", 300, 1200, 700)
        show_labels = st.sidebar.checkbox("Mostrar Valores no Gráfico", value=True)
        if tipo == "Barra" and show_labels:
            posicao_rotulos = st.sidebar.selectbox("Posição dos Rótulos", ["Fora das Barras", "Dentro das Barras", "Automático"], index=0)
            pos_map = {"Fora das Barras": "outside", "Dentro das Barras": "inside", "Automático": "auto"}
            text_pos = pos_map[posicao_rotulos]
            force_horizontal = st.sidebar.checkbox("Forçar Rótulos Horizontais (Evita Rotação)", value=True)
        else:
            text_pos = "auto"
            force_horizontal = False

        st.sidebar.divider()
        st.sidebar.subheader("🔡 Tamanho das Fontes")
        font_titulo    = st.sidebar.slider("Título",        8, 40, 14)
        font_subtitulo = st.sidebar.slider("Subtítulo",     6, 30, 11)
        font_eixo      = st.sidebar.slider("Rótulo dos Eixos", 8, 36, 13)
        font_ticks     = st.sidebar.slider("Escala dos Eixos",  8, 36, 12)
        font_legenda   = st.sidebar.slider("Legenda",        8, 36, 12)
        font_rotulos   = st.sidebar.slider("Valores nas Barras", 8, 36, 12)

        def preparar_dados():
            """Prepara e retorna o df_plot e c_order com base nos filtros selecionados."""
            if not segs or not opcoes_selecionadas or not campus_selecionados:
                return None, None
            df_q = df_campus[df_campus["Pergunta"] == perg].copy()
            df_q = df_q[df_q["Opcao"].isin(opcoes_selecionadas)]
            df_q = df_q[df_q["Segmento"].isin(segs)]
            # Soma os valores de todos os campus selecionados por Segmento + Opção
            df_q = df_q.groupby(["Segmento", "Opcao"], as_index=False).agg(
                {"Quantidade": "sum", "Ordem_Ref": "min"}
            )
            ops = df_q["Opcao"].unique()
            template = pd.MultiIndex.from_product([segs, ops], names=["Segmento", "Opcao"]).to_frame(index=False)
            df_p = pd.merge(template, df_q, on=["Segmento", "Opcao"], how="left").fillna(0)

            if ordem == "Original":
                o_map = df_q.groupby("Opcao")["Ordem_Ref"].min().to_dict()
                df_p = df_p.sort_values(["Segmento", "Opcao"], key=lambda x: x.map(o_map) if x.name == "Opcao" else x)
            elif ordem == "Lógica (Pos→Neg)":
                df_p["Opcao"] = pd.Categorical(df_p["Opcao"], categories=[o for o in ORDEM_LOGICA if o in ops] + [x for x in ops if x not in ORDEM_LOGICA], ordered=True)
                df_p = df_p.sort_values(["Segmento", "Opcao"])
            elif ordem == "Crescente":
                o_val = df_p.groupby("Opcao")["Quantidade"].mean().sort_values().index
                df_p["Opcao"] = pd.Categorical(df_p["Opcao"], categories=o_val, ordered=True)
                df_p = df_p.sort_values(["Segmento", "Opcao"])
            elif ordem == "Decrescente":
                o_val = df_p.groupby("Opcao")["Quantidade"].mean().sort_values(ascending=False).index
                df_p["Opcao"] = pd.Categorical(df_p["Opcao"], categories=o_val, ordered=True)
                df_p = df_p.sort_values(["Segmento", "Opcao"])

            df_p["Total"] = df_p.groupby("Segmento")["Quantidade"].transform("sum")
            df_p["Percent_Num"] = (df_p["Quantidade"] / df_p["Total"] * 100).fillna(0).round(2)

            c_ord = df_p["Opcao"].unique().tolist()

            if agrupar_sentimento:
                df_p["Opcao"] = df_p["Opcao"].map(SENTIMENT_MAP).fillna(df_p["Opcao"])
                df_p = df_p.groupby(["Segmento", "Opcao"], as_index=False).agg({"Quantidade": "sum", "Total": "first"})
                df_p["Percent_Num"] = (df_p["Quantidade"] / df_p["Total"] * 100).fillna(0).round(2)
                s_order = ["Positiva", "Neutro", "Negativa"]
                ops_atuais = df_p["Opcao"].unique()
                c_ord = [o for o in s_order if o in ops_atuais] + [o for o in ops_atuais if o not in s_order]

            if campo_calculado:
                df_p = df_p.groupby("Opcao", as_index=False).agg({"Quantidade": "mean", "Percent_Num": "mean"})
                df_p["Segmento"] = "<br>".join(segs)

            c_ord = df_p["Opcao"].unique().tolist()
            return df_p, c_ord

        def montar_grafico(df_plot, c_order, horizontal=False):
            """Monta e retorna a figura Plotly."""
            if len(campus_selecionados) == 1:
                label_campus = campus_selecionados[0]
            else:
                label_campus = f"{len(campus_selecionados)} campus combinados"
            titulo = f"<b>{label_campus} - {dim}</b><br><sup>{perg}</sup>"
            y_col = "Percent_Num" if formato_valor == "Porcentagem" else "Quantidade"
            y_label = "%" if formato_valor == "Porcentagem" else "Quantidade"

            if formato_valor == "Porcentagem":
                text_template = '%{x:.1f}%' if horizontal else '%{y:.1f}%'
                text_auto = '.1f'
            else:
                if horizontal:
                    text_template = '%{x:.1f}' if campo_calculado else '%{x:.0f}'
                else:
                    text_template = '%{y:.1f}' if campo_calculado else '%{y:.0f}'
                text_auto = '.1f' if campo_calculado else '.0f'

            color_col = "Opcao" if agrupar_sentimento and campo_calculado else "Segmento"
            color_map = SENTIMENT_COLORS if color_col == "Opcao" else None

            if tipo == "Linha":
                if horizontal:
                    fig = px.line(df_plot, y="Opcao", x=y_col, color="Segmento", markers=True,
                                  category_orders={"Opcao": c_order}, title=titulo)
                else:
                    fig = px.line(df_plot, x="Opcao", y=y_col, color="Segmento", markers=True,
                                  category_orders={"Opcao": c_order}, title=titulo)
                if show_labels:
                    fig.update_traces(
                        textposition="middle right" if horizontal else "top center",
                        texttemplate=text_template,
                        mode="lines+markers+text"
                    )
            elif tipo == "Barra":
                if horizontal:
                    fig = px.bar(df_plot, y="Opcao", x=y_col, color=color_col, barmode="group",
                                 category_orders={"Opcao": c_order}, title=titulo, orientation="h",
                                 color_discrete_map=color_map,
                                 text_auto=text_auto if show_labels else False)
                    if show_labels:
                        fig.update_traces(textposition=text_pos, textangle=0 if force_horizontal else None)
                else:
                    fig = px.bar(df_plot, x="Opcao", y=y_col, color=color_col, barmode="group",
                                 category_orders={"Opcao": c_order}, title=titulo,
                                 color_discrete_map=color_map,
                                 text_auto=text_auto if show_labels else False)
                    if show_labels:
                        fig.update_traces(textposition=text_pos, textangle=0 if force_horizontal else None)
            else:
                fig = px.pie(df_plot, names="Opcao", values=y_col, facet_col="Segmento", facet_col_wrap=2, title=titulo)
                if show_labels:
                    fig.update_traces(textinfo='value+label' if formato_valor == "Absoluto" else 'percent+label')

            if horizontal:
                fig.update_layout(
                    width=c_width, height=c_height, margin=dict(t=100, r=50),
                    xaxis_title=y_label, yaxis_title="",
                    title_font_size=font_titulo,
                    xaxis=dict(title_font_size=font_eixo, tickfont_size=font_ticks),
                    yaxis=dict(title_font_size=font_eixo, tickfont_size=font_ticks),
                    legend=dict(font_size=font_legenda),
                )
            else:
                fig.update_layout(
                    width=c_width, height=c_height, margin=dict(t=100, r=300),
                    yaxis_title=y_label, xaxis_title="",
                    title_font_size=font_titulo,
                    xaxis=dict(title_font_size=font_eixo, tickfont_size=font_ticks),
                    yaxis=dict(title_font_size=font_eixo, tickfont_size=font_ticks),
                    legend=dict(font_size=font_legenda),
                )
            # Aplica tamanho de fonte nos rótulos de dados (barras/linhas)
            fig.update_traces(textfont_size=font_rotulos)
            # Ajusta o subtítulo (texto dentro do <sup>)
            fig.update_layout(title=dict(
                text=titulo,
                font=dict(size=font_titulo),
            ))
            return fig

        # --- Gráfico ---
        df_plot, c_order = preparar_dados()

        if df_plot is not None:
            fig = montar_grafico(df_plot, c_order, horizontal=False)
            # Nome do arquivo da câmera = dimensão + pergunta (sanitizado)
            import re as _re
            _nome_base = f"{dim} - {perg}"
            _nome_arquivo = _re.sub(r'[\\/*?:"<>|]', '', _nome_base)[:150]
            _config = {"toImageButtonOptions": {"filename": _nome_arquivo}}
            st.plotly_chart(fig, use_container_width=False, config=_config)
            c1, c2 = st.columns(2)
            with c1:
                st.download_button("📊 Baixar Excel", to_excel(df_plot[["Segmento", "Opcao", "Quantidade", "Percent_Num"]]), "cpa_resultado.xlsx")
            with c2:
                st.download_button("🌐 Baixar HTML", fig.to_html(include_plotlyjs='cdn'), "grafico.html")
            st.info("💡 **Dica para Imagem HD**: Ajuste o tamanho acima e clique no ícone da **CÂMERA** no canto superior do gráfico.")
            st.dataframe(df_plot[["Segmento", "Opcao", "Quantidade", "Percent_Num"]], use_container_width=True)
        else:
            if not campus_selecionados:
                st.warning("⚠️ Selecione ao menos um campus.")
            else:
                st.warning("⚠️ Selecione ao menos um segmento e uma opção de resposta.")
