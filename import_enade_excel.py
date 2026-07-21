import pandas as pd
import numpy as np

def parse_enade_excel(file_bytes):
    df_raw = pd.read_excel(file_bytes, header=None)
    records = []
    
    current_indicador = None
    current_ano = None
    
    # State machine for parsing
    # row formats:
    # "Número Indicador" | "1"
    # "Indicador" | "N. de participantes do ENADE"
    # "Ano" | "2014"
    # "cidade" | "Macapá"
    # "curso:" | "Tipo" | "População" | "Presentas"
    # "Engenharia de Pesca" | "Bacharelado" | 6 | 0
    #
    # "Pergunta:" | "Ao longo da..."
    # "cidade" | "Macapá"
    # "Resposta" | "Curso" | "UF" | "Região" | "Brasil"
    # "Nenhum" | 39.1 | 53.3 | ...
    
    i = 0
    while i < len(df_raw):
        row = df_raw.iloc[i]
        
        # Ignora linhas totalmente vazias
        if row.isna().all():
            i += 1
            continue
            
        cell0 = str(row[0]).strip() if pd.notna(row[0]) else ""
        
        if cell0.startswith("Número Indicador"):
            num_ind = str(row[1]).strip() if len(row) > 1 and pd.notna(row[1]) else ""
            
            i += 1
            if i < len(df_raw):
                row_ind = df_raw.iloc[i]
                val0 = str(row_ind[0]).strip() if pd.notna(row_ind[0]) else ""
                
                if "indicador" in val0.lower() or "inidicador" in val0.lower():
                    nome_ind = str(row_ind[1]).strip() if len(row_ind) > 1 and pd.notna(row_ind[1]) else ""
                    current_indicador = f"{num_ind} - {nome_ind}"
                elif val0 != "Ano" and val0 != "curso:":
                    if len(val0) > 3 and not val0.replace('.','',1).isdigit():
                        current_indicador = val0
                    elif len(row_ind) > 1 and pd.notna(row_ind[1]):
                        current_indicador = f"{num_ind} - {str(row_ind[1]).strip()}"
                    else:
                        current_indicador = str(num_ind)
                        i -= 1
                else:
                    current_indicador = str(num_ind)
                    i -= 1
            i += 1
            continue
            
        elif "indicador" in cell0.lower() or "inidicador" in cell0.lower():
            # Caso não tenha "Número Indicador" e venha direto o "Indicador"
            current_indicador = str(row[1]).strip() if len(row) > 1 and pd.notna(row[1]) else ""
            i += 1
            continue
            
        elif cell0 == "Ano":
            try:
                # O PDF as vezes mostra "2014 Conceito Enade"
                ano_str = str(row[1]).split()[0]
                current_ano = int(float(ano_str))
            except:
                current_ano = None
            i += 1
            continue
            
        elif cell0 == "Pergunta:":
            # Ignoramos a pergunta por enquanto, ela está embutida no current_indicador (geralmente 5 ou 6)
            i += 1
            continue
            
        elif cell0 == "cidade":
            # Cidade não nos interessa salvar
            i += 1
            continue
            
        elif cell0.lower() == "tipo":
            # Ignora a linha de tipo antes das respostas se existir
            i += 1
            continue
            
        elif cell0.lower() in ["curso:", "curso", "resposta"]:
            # Cabeçalho de tabela
            # Pode ser: "curso:" | "Tipo" | "População" | "Presentas"
            # Ou: "Curso" | "Engenharia Florestal"
            
            val1 = str(row[1]).strip().lower() if pd.notna(row[1]) else ""
            if (cell0.lower() == "curso" or cell0.lower() == "curso:") and val1 != "tipo" and len(val1) > 3:
                # Trata caso de cabeçalho "Curso | Nome do Curso" antes das respostas (Layout 2)
                curso_atual = str(row[1]).strip()
                i += 1
                
                # A próxima linha pode ser 'tipo | Bacharelado' ou 'Resposta | Curso | UF...'
                # Vamos pular linhas até achar 'Resposta'
                while i < len(df_raw):
                    row_header = df_raw.iloc[i]
                    if pd.notna(row_header[0]) and str(row_header[0]).strip() == "Resposta":
                        break
                    i += 1
                
                if i < len(df_raw):
                    row_header = df_raw.iloc[i]
                    metricas = [str(m).strip() for m in row_header[1:] if pd.notna(m)]
                    i += 1
                    
                    # Agora vêm as respostas
                    while i < len(df_raw):
                        row_resp = df_raw.iloc[i]
                        if row_resp.isna().all() or not pd.notna(row_resp[0]):
                            break
                        resp_text = str(row_resp[0]).strip()
                        if resp_text in ["Curso", "cidade", "Ano", "Número Indicador", "Pergunta:"]:
                            break
                            
                        # Lê os valores
                        for idx_m, metrica in enumerate(metricas):
                            val_col = idx_m + 1
                            if val_col < len(row_resp) and pd.notna(row_resp[val_col]):
                                try:
                                    val_str = str(row_resp[val_col]).replace(',', '.')
                                    if val_str.upper() not in ["NAN", "NA", "NULL"]:
                                        val = float(val_str)
                                        if pd.notna(val) and not np.isnan(val):
                                            records.append({
                                                "indicador": current_indicador,
                                                "ano": current_ano,
                                                "curso": curso_atual,
                                                "sub_categoria": resp_text,
                                                "metrica": metrica,
                                                "valor": val
                                            })
                                except:
                                    pass
                        i += 1
                    continue
            else:
                # É um cabeçalho padrão: "curso:" | "Tipo" | "População" | "Presentas"
                metricas = [str(c).strip() for c in row[2:] if pd.notna(c)]
                
                # Para o Indicador 2, o cabeçalho 'Conceito Enade' fica na linha de cima ('cidade')
                if not metricas and i > 0:
                    row_above = df_raw.iloc[i-1]
                    metricas = [str(c).strip() for c in row_above[2:] if pd.notna(c)]
                
                i += 1
                while i < len(df_raw):
                    row_data = df_raw.iloc[i]
                    if row_data.isna().all() or not pd.notna(row_data[0]):
                        break
                    
                    curso_nome = str(row_data[0]).strip()
                    if curso_nome in ["Curso", "cidade", "Ano", "Número Indicador", "Pergunta:", "total"]:
                        break
                        
                    for idx_m, metrica in enumerate(metricas):
                        val_col = idx_m + 2
                        if val_col < len(row_data) and pd.notna(row_data[val_col]):
                            try:
                                val_str = str(row_data[val_col]).replace(',', '.')
                                if val_str.upper() not in ["NAN", "NA", "NULL"]:
                                    val = float(val_str)
                                    if pd.notna(val) and not np.isnan(val):
                                        records.append({
                                            "indicador": current_indicador,
                                            "ano": current_ano,
                                            "curso": curso_nome,
                                            "sub_categoria": None,
                                            "metrica": metrica,
                                            "valor": val
                                        })
                            except:
                                pass
                    i += 1
                continue
                
        i += 1
        
    return records
