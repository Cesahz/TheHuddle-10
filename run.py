from app import create_app

#crear la instancia de la aplicacion
app = create_app()

if __name__ == '__main__':
    #ejecuta el servidor en modo debug para desarrollo
    app.run(debug=True)