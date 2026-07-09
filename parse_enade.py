import pdfplumber
import pandas as pd
import re

def parse_enade_pdf(file_bytes, filename="PDF"):
    """
    Extrai tabelas de um relatório original do INEP (ENADE).
    Retorna uma lista de dicionários mapeados para a tabela enade_dados.
    """
    records = []
    
    # Tenta descobrir o ano do ENADE pelo nome do arquivo
    ano_enade = 2023
    m_ano = re.search(r'20\d{2}', filename)
    if m_ano:
        ano_enade = int(m_ano.group(0))

    try:
        with pdfplumber.open(file_bytes) as pdf:
            primeira_pag = pdf.pages[0].extract_text()
            if primeira_pag:
                m_ano_capa = re.search(r'ENADE[^\d]*?(20\d{2})', primeira_pag.upper())
                if m_ano_capa:
                    ano_enade = int(m_ano_capa.group(1))

            curso_atual = "Curso Desconhecido"

            for page in pdf.pages:
                tables = page.extract_tables()
                if not tables:
                    continue
                
                page_text = page.extract_text() or ""
                # Tenta descobrir o curso atual na página (útil para Indicadores 5, 6, etc que são tabelas por curso)
                m_curso = re.search(r'([A-ZÇÃÁÂÉÊÍÓÔÚ\s]+)\s*-\s*\d+', page_text)
                if m_curso:
                    curso_txt = m_curso.group(1).strip()
                    if "Tabela" not in curso_txt and "Quadro" not in curso_txt:
                        curso_atual = curso_txt
                
                for table in tables:
                    if not table or len(table) < 2:
                        continue
                    
                    clean_table = []
                    for row in table:
                        clean_row = []
                        for cell in row:
                            if cell:
                                clean_row.append(str(cell).replace('\n', ' ').strip())
                            else:
                                clean_row.append("")
                        clean_table.append(clean_row)
                    
                    header = clean_table[0]
                    header_str = " | ".join(header).upper()

                    # Indicador 1: Participantes (População e Presentes)
                    if "POPULAÇÃO" in header_str and "PRESENTES" in header_str:
                        idx_pop = -1
                        idx_pres = -1
                        idx_curso = 0
                        for i, col in enumerate(header):
                            col_up = col.upper()
                            if "POPULAÇÃO" in col_up: idx_pop = i
                            if "PRESENTES" in col_up: idx_pres = i
                        
                        if idx_pop != -1 and idx_pres != -1:
                            for row in clean_table[1:]:
                                if len(row) > max(idx_pop, idx_pres):
                                    curso = row[idx_curso]
                                    if not curso or "IES" in curso.upper() or "ÁREA" in curso.upper():
                                        continue
                                    
                                    pop_val = row[idx_pop]
                                    pres_val = row[idx_pres]
                                    
                                    if pop_val.isdigit():
                                        records.append({
                                            "indicador": "1 - N. de participantes do ENADE",
                                            "ano": ano_enade,
                                            "curso": curso,
                                            "sub_categoria": None,
                                            "metrica": "População",
                                            "valor": float(pop_val)
                                        })
                                    if pres_val.isdigit():
                                        records.append({
                                            "indicador": "1 - N. de participantes do ENADE",
                                            "ano": ano_enade,
                                            "curso": curso,
                                            "sub_categoria": None,
                                            "metrica": "Presentes",
                                            "valor": float(pres_val)
                                        })

                    # Indicador 2: Conceito ENADE
                    elif "CONCEITO" in header_str and "ENADE" in header_str:
                        idx_conceito = -1
                        for i, col in enumerate(header):
                            if "CONCEITO" in col.upper(): idx_conceito = i
                        if idx_conceito != -1:
                            for row in clean_table[1:]:
                                if len(row) > idx_conceito:
                                    curso = row[0]
                                    if not curso or "IES" in curso.upper() or "ÁREA" in curso.upper():
                                        continue
                                    conc_val = row[idx_conceito].replace(',', '.')
                                    try:
                                        v = float(conc_val)
                                        records.append({
                                            "indicador": "2 - Conceito ENADE",
                                            "ano": ano_enade,
                                            "curso": curso,
                                            "sub_categoria": None,
                                            "metrica": "Conceito ENADE",
                                            "valor": v
                                        })
                                    except ValueError:
                                        pass

                    # Indicadores 5 e 6: "Curso, UF, Região, Cat. Adm., Org. Acad., Brasil"
                    elif "CURSO" in header_str and "BRASIL" in header_str and "REGIÃO" in header_str:
                        primeira_col = header[0].upper()
                        
                        indicador_nome = "Questionário do Estudante"
                        if "RENDA" in primeira_col:
                            indicador_nome = "Renda Familiar"
                        elif "ESCOLARIZAÇÃO" in primeira_col:
                            indicador_nome = "Escolaridade Pais"
                        elif "BOLSA" in primeira_col:
                            indicador_nome = "6 - Recebimento de bolsa acadêmica"
                        elif "AUXÍLIO" in primeira_col:
                            indicador_nome = "5 - Recebimento de auxílio permanência"
                        
                        col_map = {}
                        for i, col in enumerate(header):
                            if i == 0: continue
                            c_up = col.upper()
                            if "CURSO" in c_up or "IES" in c_up: col_map[i] = "Curso"
                            elif "UF" in c_up: col_map[i] = "UF"
                            elif "REGIÃO" in c_up: col_map[i] = "Região"
                            elif "ADM" in c_up: col_map[i] = "Cat. Adm."
                            elif "ACAD" in c_up: col_map[i] = "Org. Acad."
                            elif "BRASIL" in c_up: col_map[i] = "Brasil"
                        
                        for row in clean_table[1:]:
                            sub_categoria = row[0]
                            if not sub_categoria or "Tabela" in sub_categoria:
                                continue
                            
                            for col_idx, metrica in col_map.items():
                                if len(row) > col_idx:
                                    val_str = row[col_idx].replace(',', '.')
                                    try:
                                        v = float(val_str)
                                        records.append({
                                            "indicador": indicador_nome,
                                            "ano": ano_enade,
                                            "curso": curso_atual,
                                            "sub_categoria": sub_categoria,
                                            "metrica": metrica,
                                            "valor": v
                                        })
                                    except ValueError:
                                        pass

                    # Indicadores 7.x: Avaliação do Curso
                    elif "ÁREA" in header_str and "CURSO" in header_str and "BRASIL" in header_str:
                        col_map = {}
                        for i, col in enumerate(header):
                            if i == 0: continue
                            c_up = col.upper()
                            if "CURSO" in c_up or "IES" in c_up: col_map[i] = "Curso"
                            elif "UF" in c_up: col_map[i] = "UF"
                            elif "REGIÃO" in c_up: col_map[i] = "Região"
                            elif "ADM" in c_up: col_map[i] = "Cat. Adm."
                            elif "ACAD" in c_up: col_map[i] = "Org. Acad."
                            elif "BRASIL" in c_up: col_map[i] = "Brasil"
                            
                        for row in clean_table[1:]:
                            curso_nome = row[0].split('-')[0].strip() if '-' in row[0] else row[0]
                            if not curso_nome or "Tabela" in curso_nome or "Área" in curso_nome:
                                continue
                            
                            for col_idx, metrica in col_map.items():
                                if len(row) > col_idx:
                                    val_str = row[col_idx].replace(',', '.')
                                    try:
                                        v = float(val_str)
                                        records.append({
                                            "indicador": "7 - Avaliação do Curso (Questionário)",
                                            "ano": ano_enade,
                                            "curso": curso_nome,
                                            "sub_categoria": "Percentual Concordância",
                                            "metrica": metrica,
                                            "valor": v
                                        })
                                    except ValueError:
                                        pass

    except Exception as e:
        import traceback
        print(f"Erro em parse_enade_pdf: {traceback.format_exc()}")
        raise e
        
    return records
