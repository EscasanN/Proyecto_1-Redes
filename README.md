# Proyecto 1 - Redes

Nelson Estuardo Escalante Sanchez - 22046

# Descripcion

Este proyecto se conecta a servidores MCP y hace uso de herramientas brindadas por estos para acceder a nuevas funcionalidades. Tambien permite chatear con el LLM de Google (Gemini) y mantener una conversacion coherente con este.

# Uso 

Instalar las dependencias necesarias.
```bash
pip install -r requirements.txt
```

En una terminal diferente, ejecutar los servidores MCP (Ejemplo con Filesystem).
```bash
npx -y @modelcontextprotocol/server-filesystem ./workspace
```

Ejecutar el programa programa principal.
```bash
python -m app.main
```